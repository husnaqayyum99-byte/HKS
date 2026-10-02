import { useState } from "react";
import Analysis from "./Analysis.jsx";
import Describe from "./Describe.jsx";
import FollowUp from "./FollowUp.jsx";
import Results from "./Results.jsx";

const emptyProblem = { text: "", province: "" };

export default function PublicAnalysis() {
  const [stage, setStage] = useState("describe");
  const [problem, setProblem] = useState(emptyProblem);
  const [answers, setAnswers] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [result, setResult] = useState(null);

  function startAnalysis(description) {
    setProblem(description);
    setAnswers([]);
    setQuestions([]);
    setResult(null);
    setStage("analysis");
  }

  function handleAnalysisResult(analysisResult) {
    setResult(analysisResult);
    const requestedQuestions = analysisResult.follow_up_questions || [];
    if (analysisResult.status === "needs_clarification" && requestedQuestions.length > 0) {
      setQuestions(requestedQuestions);
      setStage("followup");
      return;
    }
    setStage("results");
  }

  function submitClarification(newAnswers) {
    setAnswers((current) => [...current, ...newAnswers]);
    setStage("analysis");
  }

  function restart() {
    setProblem(emptyProblem);
    setAnswers([]);
    setQuestions([]);
    setResult(null);
    setStage("describe");
  }

  if (stage === "analysis") {
    return (
      <Analysis
        problem={problem}
        answers={answers}
        onDone={handleAnalysisResult}
        onBack={() => setStage(questions.length > 0 ? "followup" : "describe")}
      />
    );
  }

  if (stage === "followup") {
    return (
      <FollowUp
        problem={problem}
        initialQuestions={questions}
        onBack={() => setStage("describe")}
        onDone={submitClarification}
      />
    );
  }

  if (stage === "results" && result) {
    return <Results result={result} problem={problem} answers={answers} onRestart={restart} />;
  }

  return <Describe initialValue={problem} onContinue={startAnalysis} />;
}