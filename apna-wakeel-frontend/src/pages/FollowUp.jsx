import { useEffect, useState } from "react";
import FlowSteps from "../components/FlowSteps.jsx";
import Button from "../components/Button.jsx";
import Alert from "../components/Alert.jsx";
import { getFollowUpQuestions } from "../services/api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

// Shows ONE question at a time. The person moves forward with "Next".
//
// Answers are stored as simple values ("yes", "no", "unsure", an option number,
// or typed text). That way, if the person switches language in the middle,
// their answers are still correct.

export default function FollowUp({ problem, onBack, onDone, initialQuestions }) {
  const { t, language } = useLanguage();
  const [questions, setQuestions] = useState(() => (initialQuestions || []).map((question, index) => (
    typeof question === "string"
      ? { id: `clarification-${index + 1}`, text: question, type: "text" }
      : question
  )));
  const [loading, setLoading] = useState(!initialQuestions);
  const [loadError, setLoadError] = useState("");
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({}); // { questionId: value }
  const [tryCount, setTryCount] = useState(0); // bump this to retry loading

  // Load the questions when this screen opens (and again if the language changes).
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError("");

    if (initialQuestions) {
      setQuestions(initialQuestions.map((question, index) => (
        typeof question === "string"
          ? { id: `clarification-${index + 1}`, text: question, type: "text" }
          : question
      )));
      setIndex(0);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    getFollowUpQuestions({ problem: problem.text, province: problem.province, language })
      .then((list) => {
        if (!cancelled) setQuestions(list);
      })
      .catch((requestError) => {
        if (import.meta.env.DEV) console.error("Follow-up question request failed:", requestError);
        if (!cancelled) setLoadError(t(requestError?.message === "api.endpointUnavailable" ? "followup.backendUnsupported" : requestError?.status === 429 ? "followup.rateLimited" : requestError?.status === 503 ? "followup.serviceUnavailable" : "followup.loadError"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [problem, tryCount, language, initialQuestions]);

  if (loading) {
    return (
      <div className="container flow-page">
        <FlowSteps current={2} />
        <div className="status" role="status">
          <span className="loader" aria-hidden="true" />
          <p>{t("followup.loading")}</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="container flow-page">
        <FlowSteps current={2} />
        <Alert tone="error" icon="alert" role="alert">
          <p>{loadError}</p>
          <div className="btn-row">
            <Button onClick={() => setTryCount(tryCount + 1)}>{t("common.tryAgain")}</Button>
            <Button variant="secondary" onClick={onBack}>
              {t("common.goBack")}
            </Button>
          </div>
        </Alert>
      </div>
    );
  }

  // The list of choices for a question: [{ value, label }]
  function getOptions(q) {
    if (q.type === "yesno") {
      return [
        { value: "yes", label: t("common.yes") },
        { value: "no", label: t("common.no") },
        { value: "unsure", label: t("common.notSure") },
      ];
    }
    return (q.options || []).map((label, i) => ({ value: String(i), label }));
  }

  // The answer as readable text, in the current language (this is what the back end receives).
  function getAnswerText(q) {
    const value = answers[q.id] || "";
    if (q.type === "text") return value;
    const found = getOptions(q).find((option) => option.value === value);
    return found ? found.label : "";
  }

  const safeIndex = Math.min(index, questions.length - 1);
  const question = questions[safeIndex];
  const total = questions.length;
  const isLast = safeIndex === total - 1;
  const currentValue = answers[question.id] || "";
  const canSkip = question.type === "text"; // free-text questions are optional
  const canContinue = currentValue.trim() !== "" || canSkip;

  function setAnswer(value) {
    setAnswers({ ...answers, [question.id]: value });
  }

  function handleNext(event) {
    event.preventDefault();
    if (!isLast) {
      setIndex(safeIndex + 1);
      return;
    }
    // Turn the answers into a simple list for the back end.
    const list = questions.map((q) => ({
      questionId: q.id,
      question: q.text,
      answer: getAnswerText(q),
    }));
    onDone(list);
  }

  function handleBack() {
    if (safeIndex === 0) onBack();
    else setIndex(safeIndex - 1);
  }

  return (
    <div className="container flow-page">
      <FlowSteps current={2} />
        {initialQuestions && (
          <header>
            <h1 className="page-title">{t("results.needsMoreInformation")}</h1>
            <p className="page-intro">{t("results.clarificationIntro")}</p>
          </header>
        )}

      <div className="form-card">
        <p className="question-count" aria-live="polite">
          {t("followup.count", { current: safeIndex + 1, total })}
        </p>
        <div className="bar" role="presentation">
          <div className="bar-fill" style={{ width: `${((safeIndex + 1) / total) * 100}%` }} />
        </div>

        {/* key={question.id} makes React start fresh for each question */}
        <form onSubmit={handleNext} className="form" key={question.id}>
          {question.type === "text" ? (
            <div className="field">
              <label htmlFor="answer" className="question-text">
                {question.text}
              </label>
              {question.hint && (
                <p id="answer-hint" className="hint">
                  {question.hint}
                </p>
              )}
              <textarea
                id="answer"
                rows={5}
                value={currentValue}
                onChange={(e) => setAnswer(e.target.value)}
                aria-describedby={question.hint ? "answer-hint" : undefined}
              />
            </div>
          ) : (
            <fieldset className="choices">
              <legend className="question-text">{question.text}</legend>
              {question.hint && <p className="hint">{question.hint}</p>}
              {getOptions(question).map((option) => (
                <label key={option.value} className={`choice ${currentValue === option.value ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name={question.id}
                    value={option.value}
                    checked={currentValue === option.value}
                    onChange={() => setAnswer(option.value)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </fieldset>
          )}

          <div className="form-actions form-actions-split">
            <Button variant="secondary" onClick={handleBack}>
              {t("common.back")}
            </Button>
            <Button type="submit" disabled={!canContinue} iconAfter="arrow">
              {isLast ? t("followup.seeAnalysis") : t("common.next")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
