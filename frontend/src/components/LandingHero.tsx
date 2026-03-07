type LandingHeroProps = {
  onEnter: () => void;
};

const VALUE_CARDS = [
  {
    icon: "\u{1F4CA}",
    title: "Composite Health Scoring",
    body: "Multi-modal health index fusing lab results, clinical notes, and prescription data into a single dynamic score per patient.",
  },
  {
    icon: "\u{1F4C9}",
    title: "VaR-Inspired Risk Quantification",
    body: "Adapts Value-at-Risk methodology from financial engineering to quantify downside health risk with Monte Carlo simulation.",
  },
  {
    icon: "\u{1F9E0}",
    title: "NLP Clinical Intelligence",
    body: "Transformer-based NLI scoring of unstructured doctor notes, nursing observations, and discharge summaries.",
  },
  {
    icon: "\u{1F50D}",
    title: "Validated Against Benchmarks",
    body: "Cross-validated against established clinical scoring systems (Charlson, APACHE-style) with statistical significance testing.",
  },
];

export default function LandingHero({ onEnter }: LandingHeroProps) {
  return (
    <section className="landing-hero" aria-label="ILAY introduction">
      <div className="landing-hero-gradient" aria-hidden="true" />
      <div className="landing-hero-particles" aria-hidden="true">
        {Array.from({ length: 22 }).map((_, idx) => (
          <span key={idx} className="landing-particle" />
        ))}
      </div>

      <div className="landing-hero-content">
        <div className="landing-logo-wrap">
          <img src="/images/ilay-logo.svg" alt="ILAY logo" className="landing-logo" />
          <div>
            <h1 className="landing-title">ILAY</h1>
            <div className="landing-subtitle-text">Clinical Risk Intelligence</div>
          </div>
        </div>

        <p className="landing-tagline">
          AI-powered health scoring platform that transforms raw clinical data into
          actionable patient risk intelligence — built for clinicians, validated against benchmarks.
        </p>

        <div className="landing-badges">
          <span className="landing-badge">ACUHIT 2026</span>
          <span className="landing-badge-separator" aria-hidden="true" />
          <span className="landing-badge">Acibadem University</span>
          <span className="landing-badge-separator" aria-hidden="true" />
          <span className="landing-badge">48-Hour Hackathon</span>
        </div>

        <div className="landing-value-grid">
          {VALUE_CARDS.map((card) => (
            <article key={card.title} className="landing-value-card">
              <div className="landing-card-header">
                <span className="landing-card-icon" aria-hidden="true">{card.icon}</span>
                <h2>{card.title}</h2>
              </div>
              <p>{card.body}</p>
            </article>
          ))}
        </div>

        <button type="button" className="landing-cta" onClick={onEnter} aria-label="Launch ILAY dashboard">
          Launch Dashboard
        </button>

        <div className="landing-team-credit">
          Built by Team ILAY
        </div>
      </div>
    </section>
  );
}
