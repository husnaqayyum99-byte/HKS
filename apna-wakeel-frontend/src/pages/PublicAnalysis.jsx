import { useState } from "react";
import Alert from "../components/Alert.jsx";
import Button from "../components/Button.jsx";
import CopyAnswerButton from "../components/CopyAnswerButton.jsx";
import ReferralPanel from "../components/ReferralPanel.jsx";
import { useLanguage } from "../i18n/LanguageContext.jsx";
import { analyzePublicCase } from "../services/api.js";

function ResultList({ title, items, statusLabels }) {
  if (!items?.length) return null;
  return (
    <section className="public-path-section">
      <h3>{title}</h3>
      <ol className="public-path-list">
        {items.map((item, index) => (
          <li key={`${item.text}-${index}`}>
            <span>{item.text}</span>
            <span className={`public-claim-status status-${item.status || "unresolved"}`}>
              {statusLabels[item.status] || statusLabels.unresolved}
            </span>
            {item.source_urls?.length > 0 && (
              <small>{item.source_urls.join(", ")}</small>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function PublicAnalysis({ onHome }) {
  const { t, language } = useLanguage();
  const [content, setContent] = useState("");
  const [history, setHistory] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const message = content.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    try {
      const analysis = await analyzePublicCase({
        content: message,
        language,
        conversationHistory: history,
      });
      setResult(analysis);
      if (analysis.status === "needs_clarification") {
        const assistantQuestion = (analysis.follow_up_questions || []).join("\n");
        setHistory((previous) => [
          ...previous,
          { role: "user", content: message },
          ...(assistantQuestion ? [{ role: "assistant", content: assistantQuestion }] : []),
        ]);
      }
      if (analysis.status !== "needs_description") setContent("");
    } catch (requestError) {
      setError(requestError?.message || "api.requestFailed");
    } finally {
      setBusy(false);
    }
  }

  function startOver() {
    setContent("");
    setHistory([]);
    setResult(null);
    setError("");
  }

  const statusLabels = {
    supported: t("publicAnalysis.supported"),
    contradicted: t("publicAnalysis.contradicted"),
    unresolved: t("publicAnalysis.unresolved"),
  };
  const completed = result && !["needs_clarification", "needs_description"].includes(result.status);

  return (
    <div className="container flow-page public-analysis-page">
      <div className="public-analysis-heading">
        <p className="eyebrow">{t("publicAnalysis.eyebrow")}</p>
        <h1>{t("publicAnalysis.title")}</h1>
        <p>{t("publicAnalysis.intro")}</p>
      </div>

      <Alert tone="info" icon="info">
        <p>{t("publicAnalysis.privacyNote")}</p>
        <p>{t("publicAnalysis.scopeNote")}</p>
      </Alert>

      {history.length > 0 && (
        <section className="public-conversation" aria-label={t("publicAnalysis.conversation")}>
          {history.map((message, index) => (
            <p key={`${index}-${message.role}`} className={`public-turn public-turn-${message.role}`}>
              <strong>{message.role === "user" ? t("publicAnalysis.you") : t("publicAnalysis.apnaWakeel")}:</strong>{" "}
              {message.content}
            </p>
          ))}
        </section>
      )}

      {error && <Alert tone="error" icon="alert" role="alert">{error}</Alert>}

      {result?.status === "needs_clarification" && (
        <Alert tone="warning" icon="info">
          <p>{t("publicAnalysis.clarificationIntro")}</p>
          <ul>
            {(result.follow_up_questions || []).map((question, index) => (
              <li key={`${index}-${question}`}>{question}</li>
            ))}
          </ul>
        </Alert>
      )}
      {result?.status === "needs_description" && (
        <Alert tone="info" icon="info" role="status">
          <p>{t("publicAnalysis.moreDescription")}</p>
        </Alert>
      )}

      <form className="public-analysis-form" onSubmit={submit}>
        <label className="field" htmlFor="public-case-description">
          <span>{t("publicAnalysis.describeLabel")}</span>
          <textarea
            id="public-case-description"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            maxLength={8000}
            required
            placeholder={t("publicAnalysis.placeholder")}
            aria-describedby="public-analysis-hint"
          />
        </label>
        <p id="public-analysis-hint" className="public-analysis-hint">{t("publicAnalysis.hint")}</p>
        <div className="public-analysis-actions">
          <Button variant="primary" type="submit" disabled={busy || !content.trim()}>
            {busy ? t("publicAnalysis.working") : t("publicAnalysis.submit")}
          </Button>
          {(result || history.length > 0) && (
            <Button variant="link" onClick={startOver} disabled={busy}>
              {t("publicAnalysis.startOver")}
            </Button>
          )}
          <Button variant="link" onClick={onHome} disabled={busy}>
            {t("publicAnalysis.backHome")}
          </Button>
        </div>
      </form>

      {result?.status === "unable_to_verify" && (
        <Alert tone="warning" icon="info" role="status">
          <p>{t("publicAnalysis.unableToVerify")}</p>
        </Alert>
      )}

      {result && result.status !== "needs_description" && (
        <article className="public-legal-path" aria-live="polite">
          <div className="public-path-header">
            <div>
              <p className="eyebrow">{t("publicAnalysis.resultEyebrow")}</p>
              <h2>{t("publicAnalysis.resultsTitle")}</h2>
            </div>
            <span className={`public-path-status status-${result.status}`}>
              {t(`publicAnalysis.status.${result.status}`)}
            </span>
          </div>

          <ReferralPanel referral={result.referral} />

          <section className="public-path-section">
            <h3>{t("publicAnalysis.understanding")}</h3>
            <p>{result.understanding || t("publicAnalysis.notEstablished")}</p>
            {result.facts?.length > 0 && <ul>{result.facts.map((fact, index) => <li key={`${index}-${fact}`}>{fact}</li>)}</ul>}
          </section>
          <dl className="public-path-facts">
            <div><dt>{t("publicAnalysis.legalArea")}</dt><dd>{result.legal_area?.replaceAll("_", " ") || t("publicAnalysis.notEstablished")}</dd></div>
            {result.legal_subtype && result.legal_subtype !== "unclear" && (
              <div><dt>{t("publicAnalysis.subtype")}</dt><dd>{result.legal_subtype.replaceAll("_", " ")}</dd></div>
            )}
            <div><dt>{t("publicAnalysis.jurisdiction")}</dt><dd>{[result.jurisdiction, result.locality].filter((item) => item && item !== "unknown").join(" · ") || t("publicAnalysis.notEstablished")}</dd></div>
            {result.incident_location && <div><dt>{t("publicAnalysis.incidentLocation")}</dt><dd>{result.incident_location}</dd></div>}
            {result.incident_type && <div><dt>{t("publicAnalysis.incidentType")}</dt><dd>{result.incident_type}</dd></div>}
            {result.vehicle_damage && <div><dt>{t("publicAnalysis.vehicleDamage")}</dt><dd>{result.vehicle_damage}</dd></div>}
            {result.responsibility_dispute !== null && result.responsibility_dispute !== undefined && (
              <div><dt>{t("publicAnalysis.responsibilityDispute")}</dt><dd>{t(result.responsibility_dispute ? "publicAnalysis.yes" : "publicAnalysis.no")}</dd></div>
            )}
            {result.compensation_dispute !== null && result.compensation_dispute !== undefined && (
              <div><dt>{t("publicAnalysis.compensationDispute")}</dt><dd>{t(result.compensation_dispute ? "publicAnalysis.yes" : "publicAnalysis.no")}</dd></div>
            )}
          </dl>

          {completed && result.answer && (
            <section className="public-path-section">
              <div className="public-answer-heading">
                <h3>{t("publicAnalysis.guidance")}</h3>
                <CopyAnswerButton content={result.answer} />
              </div>
              <p>{result.answer}</p>
            </section>
          )}

          <ResultList title={t("publicAnalysis.authority")} items={result.authorities} statusLabels={statusLabels} />
          <ResultList title={t("publicAnalysis.procedure")} items={result.procedure} statusLabels={statusLabels} />
          <ResultList title={t("publicAnalysis.documents")} items={result.documents} statusLabels={statusLabels} />
          <ResultList title={t("publicAnalysis.nextSteps")} items={result.next_steps} statusLabels={statusLabels} />

          {result.missing_information?.length > 0 && (
            <section className="public-path-section">
              <h3>{t("publicAnalysis.missingFacts")}</h3>
              <ul>{result.missing_information.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            </section>
          )}

          {result.uncertainty?.length > 0 && (
            <section className="public-path-section public-uncertainty">
              <h3>{t("publicAnalysis.uncertainty")}</h3>
              <ul>{result.uncertainty.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            </section>
          )}

          <section className="public-path-section">
            <h3>{t("publicAnalysis.sources")}</h3>
            {result.evidence?.length > 0 && (
              <p className="public-analysis-hint">{t("publicAnalysis.freshnessNote")}</p>
            )}
            {result.evidence?.length > 0 ? (
              <ul className="public-evidence-list">
                {result.evidence.map((item, index) => (
                  <li key={`${item.source_url}-${item.citation || index}`}>
                    <div className="public-evidence-title">
                      <a href={item.source_url} target="_blank" rel="noopener noreferrer">
                        {item.source_title || item.source_name}
                      </a>
                      <span className={`public-claim-status status-${item.verification_status}`}>
                        {statusLabels[item.verification_status] || statusLabels.unresolved}
                      </span>
                      {item.official_status && (
                        <span className="public-claim-status status-unresolved">{item.official_status}</span>
                      )}
                    </div>
                    <p>{item.authority}{item.jurisdiction ? ` · ${item.jurisdiction}` : ""}</p>
                    {item.citation && <p>{item.citation}</p>}
                    {item.retrieved_at && (
                      <p>{t("publicAnalysis.retrievedAt")}: {new Date(item.retrieved_at).toLocaleString(language === "ur" ? "ur-PK" : "en-PK")}</p>
                    )}
                    <blockquote>{item.excerpt}</blockquote>
                    {item.claims?.length > 0 && (
                      <ul>{item.claims.map((claim, claimIndex) => (
                        <li key={`${claim.claim}-${claimIndex}`}>
                          <span className={`public-claim-status status-${claim.status}`}>
                            {statusLabels[claim.status] || statusLabels.unresolved}
                          </span>{" "}
                          {claim.claim}
                        </li>
                      ))}</ul>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p>
                {result.status === "needs_clarification"
                  ? t("publicAnalysis.awaitingClarification")
                  : t("publicAnalysis.noEvidence")}
              </p>
            )}
          </section>
          {result.disclaimer && <p className="public-analysis-disclaimer">{result.disclaimer}</p>}
          <p className="public-analysis-disclaimer">{t("publicAnalysis.generalDisclaimer")}</p>
        </article>
      )}
    </div>
  );
}
