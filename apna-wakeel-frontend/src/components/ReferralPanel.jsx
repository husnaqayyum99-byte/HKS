import { useLanguage } from "../i18n/LanguageContext.jsx";

const REASON_KEYS = {
  emergency: "referrals.reason.emergency",
  urgent: "referrals.reason.urgent",
  high_risk: "referrals.reason.highRisk",
  legal_aid: "referrals.reason.legalAid",
  criminal_detention: "referrals.reason.detention",
  evidence_unavailable: "referrals.reason.evidenceUnavailable",
  evidence_unresolved: "referrals.reason.evidenceUnresolved",
};

function DistrictLabel({ district, t }) {
  const districtKeys = {
    "Lower Chitral": "referrals.district.lower",
    "Upper Chitral": "referrals.district.upper",
    "Chitral-wide": "referrals.district.chitralWide",
    national: "referrals.district.national",
  };
  return <>{t(districtKeys[district] || "referrals.district.chitralWide")}</>;
}

export default function ReferralPanel({ referral }) {
  const { t } = useLanguage();

  if (!referral?.recommended) return null;

  return (
    <section
      className={`referral-panel${referral.emergency ? " referral-panel-emergency" : ""}`}
      aria-labelledby="referral-panel-title"
      role={referral.emergency ? "alert" : undefined}
    >
      <h3 id="referral-panel-title">{t("results.lawyerNeedHelp")}</h3>
      <p>{t("results.lawyerFindHelp")}</p>
      {referral.emergency && <p className="referral-emergency-note">{t("referrals.emergency")}</p>}
      {referral.reasons?.length > 0 && (
        <ul className="referral-reasons">
          {referral.reasons.map((reason) => REASON_KEYS[reason] && (
            <li key={reason}>{t(REASON_KEYS[reason])}</li>
          ))}
        </ul>
      )}
      {referral.upper_chitral_contacts_unconfirmed && (
        <p className="referral-qualification">{t("referrals.upperUnconfirmed")}</p>
      )}
      {referral.resources?.length > 0 && (
        <ul className="referral-resources">
          {referral.resources.map((resource) => (
            <li key={resource.id}>
              <div className="referral-resource-heading">
                {resource.website ? (
                  <a href={resource.website} target="_blank" rel="noopener noreferrer">
                    {resource.name}
                  </a>
                ) : <strong>{resource.name}</strong>}
                <span className="referral-district"><DistrictLabel district={resource.district} t={t} /></span>
              </div>
              {resource.confidence !== "high" && (
                <span className="referral-unverified">{t("referrals.unverified")}</span>
              )}
              <p><strong>{t("referrals.confidence")}:</strong> {t(`referrals.confidence.${resource.confidence}`)}</p>
              <p><strong>{t("referrals.lastVerified")}:</strong> {resource.last_verified}</p>
              {resource.phone && <p><strong>{t("referrals.phone")}:</strong> {resource.phone}</p>}
              {resource.fax && <p><strong>{t("referrals.fax")}:</strong> {resource.fax}</p>}
              {resource.email && <p><strong>{t("referrals.email")}:</strong> {resource.email}</p>}
              {resource.notes && <p>{resource.notes}</p>}
              {resource.free_service === true && (
                <span className="referral-free-service">{t("referrals.freeService")}</span>
              )}
              <p className="referral-source">
                <strong>{t("referrals.source")}:</strong>{" "}
                <a href={resource.source_url} target="_blank" rel="noopener noreferrer">{resource.source_url}</a>
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="referral-qualification">{t("referrals.notExhaustive")}</p>
      <section className="referral-coverage-limits">
        <h4>{t("referrals.coverageLimits")}</h4>
        <ul>
          <li>{t("referrals.coverage.dlec")}</li>
          <li>{t("referrals.coverage.upper")}</li>
          <li>{t("referrals.coverage.shelter")}</li>
          <li>{t("referrals.coverage.laja")}</li>
        </ul>
      </section>
      <p className="referral-qualification">{t("referrals.qualification")}</p>
    </section>
  );
}
