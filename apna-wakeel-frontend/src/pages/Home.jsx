// Home page: hero (cover image), "what you get" strip, three steps, and About.
import { useLanguage } from "../i18n/LanguageContext.jsx";
import Icon from "../components/Icon.jsx";
import Logo from "../components/Logo.jsx";
import Button from "../components/Button.jsx";
import heroUrl from "../assets/hero.jpg";

const steps = [
  { number: 1, icon: "pencil" },
  { number: 2, icon: "bulb" },
  { number: 3, icon: "flag" },
];

// The six things the person receives on the Results page (labels reuse the Results headings).
const outcomes = [
  { icon: "scale", key: "results.legalArea" },
  { icon: "landmark", key: "results.authority" },
  { icon: "route", key: "results.timeline" },
  { icon: "file", key: "results.documents" },
  { icon: "camera", key: "results.evidence" },
  { icon: "check", key: "results.actionPlan" },
];

export default function Home({ onStart, onPublicAnalysis }) {
  const { t } = useLanguage();

  return (
    <>
      <section className="hero" aria-labelledby="hero-title">
        {/* The cover image is decorative, so it has an empty alt. A light shade on the text side keeps the words readable. */}
        <div className="hero-media" aria-hidden="true">
          <img src={heroUrl} alt="" />
          <div className="hero-overlay" />
        </div>

        <div className="container hero-inner">
          <div className="hero-copy">
            <p className="eyebrow">{t("hero.eyebrow")}</p>
            <h1 id="hero-title">
              {t("hero.line1")}
              <br />
              {t("hero.line2")}
            </h1>
            <p className="lead">{t("hero.lead")}</p>
            <div className="btn-row">
              <Button variant="accent" size="lg" iconAfter="arrow" onClick={onStart}>
                {t("nav.startNow")}
              </Button>
              <Button variant="ondark" size="lg" href="#how-it-works">
                {t("how.title")}
              </Button>
              <Button variant="ondark" size="lg" icon="message" onClick={onPublicAnalysis}>
                {t("publicAnalysis.open")}
              </Button>
            </div>
          </div>
        </div>
      </section>

      <div className="container outcomes-wrap">
        <section className="outcomes" aria-labelledby="outcomes-title">
          <h2 id="outcomes-title" className="outcomes-title">
            {t("home.outcomesTitle")}
          </h2>
          <ul>
            {outcomes.map((item) => (
              <li key={item.key} className="outcome">
                <span className="icon-badge" aria-hidden="true">
                  <Icon name={item.icon} size={22} />
                </span>
                <span>{t(item.key)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section id="how-it-works" className="section" aria-labelledby="how-title">
        <div className="container">
          <h2 id="how-title">{t("how.title")}</h2>
          <p className="section-intro">{t("how.intro")}</p>

          <ol className="steps">
            {steps.map(({ number, icon }) => (
              <li key={number} className="step-card">
                <div className="step-top">
                  <span className="icon-badge icon-badge-large" aria-hidden="true">
                    <Icon name={icon} size={26} />
                  </span>
                  <span className="step-number" aria-hidden="true">
                    0{number}
                  </span>
                </div>
                <h3>
                  <span className="visually-hidden">{t("how.stepWord", { n: number })}</span>
                  {t(`step${number}.title`)}
                </h3>
                <p>{t(`step${number}.text`)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="about" className="section section-alt" aria-labelledby="about-title">
        <div className="container about-grid">
          <div>
            <h2 id="about-title">{t("about.title")}</h2>
            <p>{t("about.p1")}</p>
            <p>{t("about.p2")}</p>
          </div>
          <div className="about-emblem">
            <Logo size={240} />
          </div>
        </div>
      </section>
    </>
  );
}
