import FlowSteps from "../components/FlowSteps.jsx";
import Button from "../components/Button.jsx";
import Badge from "../components/Badge.jsx";
import Alert from "../components/Alert.jsx";
import Icon from "../components/Icon.jsx";
import ResultSection from "../components/ResultSection.jsx";
import Checklist from "../components/Checklist.jsx";
import Timeline from "../components/Timeline.jsx";
import ActionPlan from "../components/ActionPlan.jsx";
import SourceCard from "../components/SourceCard.jsx";
import LawyerRecommendation from "../components/LawyerRecommendation.jsx";
import CaseAssessment from "../components/CaseAssessment.jsx";
import { useLanguage } from "../i18n/LanguageContext.jsx";

// The Results page. Everything shown here (except the person's own words) comes from `result`,
// so it can be filled by the back end. Optional parts only appear if the back end sends them.

export default function Results({ result, problem, answers = [], onRestart }) {
  const { t } = useLanguage();

  // The intro sentence has the province in bold, in the middle of the sentence.
  const provinceName = t(`province.${problem.province}`);
  const [introBefore, introAfter] = t("results.intro").split("{province}");

  const firstStep = result.actionPlan && result.actionPlan[0];
  const answered = answers.filter((a) => a.answer && a.answer.trim() !== "");
  const evidenceUnavailable = result.status === "evidence_unavailable" || result.sourceStatus === "none";

  if (evidenceUnavailable) {
    const unavailableQuestions = result.follow_up_questions || [];
    return (
      <div className="container flow-page results">
        <FlowSteps current={4} />
        <header className="results-header">
          <h1 className="page-title">{t("results.noSources")}</h1>
        </header>

        <Alert tone="warning" icon="alert" role="status">
          {result.explanation?.[0] || t("results.noSources")}
        </Alert>

        <ResultSection id="situation" title={t("results.situation")} icon="user">
          <blockquote className="quote">{problem.text}</blockquote>
          {result.intake?.problem_summary && <p>{result.intake.problem_summary}</p>}
        </ResultSection>

        {unavailableQuestions.length > 0 && (
          <ResultSection id="clarification" title={t("results.needsMoreInformation")} icon="info">
            <ul className="plain-list">
              {unavailableQuestions.slice(0, 3).map((question) => <li key={question}>{question}</li>)}
            </ul>
          </ResultSection>
        )}

        <section className="result-card action-card">
          <div className="action-head">
            <Icon name="check" size={22} />
            <h2>{t("results.limitedNextStepTitle")}</h2>
          </div>
          <p>{t("results.limitedNextStep")}</p>
        </section>

        <Alert tone="info" icon="info">{t("results.disclaimer")}</Alert>
        <div className="form-actions">
          <Button onClick={onRestart}>{t("results.restart")}</Button>
        </div>
      </div>
    );
  }

  // The "On this page" links (only for sections that exist)
  const jumpLinks = [
    { id: "situation", label: t("results.situation") },
    { id: "legal-area", label: t("results.legalArea") },
    { id: "explanation", label: t("results.explanation") },
    result.relevantInfo && { id: "relevant-info", label: t("results.relevantInfo") },
    result.authority && { id: "authority", label: t("results.authority") },
    result.timeline?.length > 0 && { id: "procedure", label: t("results.timeline") },
    { id: "documents", label: t("results.documents") },
    { id: "evidence", label: t("results.evidence") },
    result.lawyerType && { id: "lawyer-type", label: t("results.lawyerType") },
    result.caseAssessment && { id: "case-assessment", label: t("results.caseAssessment") },
    { id: "action-plan", label: t("results.actionPlan") },
    { id: "sources", label: t("results.sources") },
  ].filter(Boolean);

  return (
    <div className="container flow-page results">
      <FlowSteps current={4} />

      {result.isDemo && (
        <Alert tone="warning" icon="alert">
          <strong>{t("results.demoBold")}</strong> {t("results.demoText")}
        </Alert>
      )}

      <header className="results-header">
        <Badge tone="gold">{result.legalArea.tag}</Badge>
        <h1 className="page-title">{t("results.title")}</h1>
        <p className="page-intro">
          {introBefore}
          <strong>{provinceName}</strong>
          {introAfter}
        </p>
      </header>

      {result.sourceStatus === "none" && (
        <Alert tone="warning" icon="alert" role="status">{t("results.noSources")}</Alert>
      )}

      {result.status === "needs_follow_up" && (
        <Alert tone="warning" icon="alert" role="status">
          {t("results.needsMoreInformation")}
          <ul>{(result.follow_up_questions || []).map((question) => <li key={question}>{question}</li>)}</ul>
        </Alert>
      )}

      <div className="results-layout">
        {/* Summary: answers "what did you find, and what do I do now?" at a glance */}
        <aside className="summary" aria-labelledby="summary-title">
          <h2 id="summary-title">{t("results.quick")}</h2>
          <dl>
            <div>
              <dt>{t("results.legalArea")}</dt>
              <dd>{result.legalArea.name}</dd>
            </div>
            {result.authority && <div><dt>{t("results.authority")}</dt><dd>{result.authority.name}</dd></div>}
            {firstStep && (
              <div>
                <dt>{t("results.firstStep")}</dt>
                <dd>{firstStep.title}</dd>
              </div>
            )}
          </dl>

          <nav className="jump" aria-label={t("results.onThisPage")}>
            <p className="jump-title">{t("results.onThisPage")}</p>
            <ul>
              {jumpLinks.map((link) => (
                <li key={link.id}>
                  <a href={`#${link.id}`}>{link.label}</a>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        <div className="results-main">
          {/* 1. Your situation (the person's own words, so they can see what was understood) */}
          <ResultSection id="situation" title={t("results.situation")} icon="user">
            <blockquote className="quote">{problem.text}</blockquote>
            {result.intake?.problem_summary && <p>{result.intake.problem_summary}</p>}
            <p className="meta">
              <strong>{t("describe.provinceLabel")}:</strong> {provinceName}
            </p>
            {answered.length > 0 && (
              <>
                <h3 className="subheading">{t("results.yourAnswers")}</h3>
                <dl className="answers">
                  {answered.map((a) => (
                    <div key={a.questionId}>
                      <dt>{a.question}</dt>
                      <dd>{a.answer}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </ResultSection>

          {/* 2. Legal area */}
          <ResultSection id="legal-area" title={t("results.legalArea")} icon="scale">
            <p className="big-label">{result.legalArea.name}</p>
            {result.classification?.jurisdiction && <p>{result.classification.jurisdiction}{result.classification.locality && result.classification.locality !== "unknown" ? ` · ${result.classification.locality}` : ""}</p>}
          </ResultSection>

          {/* 3. What this means, in plain language */}
          <ResultSection id="explanation" title={t("results.explanation")} icon="info">
            {result.explanation.map((paragraph, i) => (
              <p key={i}>{paragraph}</p>
            ))}
          </ResultSection>

          {/* 4. Relevant legal information (optional) */}
          {result.relevantInfo && result.relevantInfo.length > 0 && (
            <ResultSection id="relevant-info" title={t("results.relevantInfo")} icon="book">
              <ul className="info-list">
                {result.relevantInfo.map((item) => (
                  <li key={item.title}>
                    <h3>{item.title}</h3>
                    <p>{item.text}</p>
                  </li>
                ))}
              </ul>
            </ResultSection>
          )}

          {/* 5. Responsible authority */}
          {result.authority && (
            <ResultSection id="authority" title={t("results.authority")} icon="landmark">
              <div className="authority">
                <h3>{result.authority.name}</h3>
                <p>{result.authority.description}</p>
                <ul className="plain-list">
                  {(result.authority.howToReach || []).map((line) => <li key={line}>{line}</li>)}
                </ul>
              </div>
            </ResultSection>
          )}

          {/* 6. Procedure */}
          {result.timeline?.length > 0 && (
            <ResultSection id="procedure" title={t("results.timeline")} icon="route">
              <Timeline items={result.timeline} />
            </ResultSection>
          )}

          {/* 7 and 8. Documents and evidence, side by side on wide screens */}
          <div className="two-col">
            <ResultSection id="documents" title={t("results.documents")} icon="file">
              <Checklist name="doc" items={result.documents || []} />
            </ResultSection>
            <ResultSection id="evidence" title={t("results.evidence")} icon="camera">
              <Checklist name="evi" items={result.evidence || []} />
            </ResultSection>
          </div>

          {/* 9. Which type of lawyer may help (optional, orientation only) */}
          <LawyerRecommendation lawyerType={result.lawyerType} hasLegalAid={result.legalAid?.show} />

          {/* 10. Case assessment (optional; never a prediction of the outcome) */}
          <CaseAssessment assessment={result.caseAssessment} />

          {/* 11. Step-by-step action plan */}
          <section className="result-card action-card" id="action-plan" aria-labelledby="action-plan-title">
            <div className="action-head">
              <Icon name="check" size={22} />
              <h2 id="action-plan-title">{t("results.actionPlan")}</h2>
            </div>
            <ActionPlan items={result.actionPlan || []} />
          </section>

          {/* 10. Sources */}
          <ResultSection id="sources" title={t("results.sources")} icon="shield">
            <ul className="source-list">
              {(result.sources || []).map((source, index) => (
                <SourceCard key={`${source.title}-${index}`} source={source} />
              ))}
            </ul>
            {(!result.sources || result.sources.length === 0) && <p>{t("results.noSources")}</p>}
          </ResultSection>

          {/* 11. Legal aid, only when the back end says it is relevant */}
          {result.legalAid && result.legalAid.show && (
            <aside className="legal-aid" id="legal-aid" aria-labelledby="legal-aid-title">
              <div className="legal-aid-head">
                <Icon name="heart" size={24} />
                <h2 id="legal-aid-title">{result.legalAid.title}</h2>
              </div>
              <p>{result.legalAid.text}</p>
              <ul className="plain-list">
                {result.legalAid.options.map((option) => (
                  <li key={option}>{option}</li>
                ))}
              </ul>
            </aside>
          )}

          {/* Gentle disclaimer */}
          <Alert tone="info" icon="info">
            {t("results.disclaimer")}
          </Alert>

          <div className="btn-row results-actions">
            <Button icon="printer" onClick={() => window.print()}>
              {t("results.print")}
            </Button>
            <Button variant="secondary" icon="restart" onClick={onRestart}>
              {t("results.restart")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
