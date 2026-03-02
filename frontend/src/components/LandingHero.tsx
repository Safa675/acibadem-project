type LandingHeroProps = {
  onEnter: () => void;
};

const VALUE_CARDS = [
  {
    title: "Finance Logic for Clinical Risk",
    body: "Translates portfolio risk principles into patient-level health risk monitoring.",
  },
  {
    title: "VaR-Inspired Health Scoring",
    body: "Quantifies downside risk using probabilistic health trajectories, not static snapshots.",
  },
  {
    title: "AI Clinical Assistant",
    body: "Provides context-aware chat guidance grounded in each patient's profile and trend signals.",
  },
  {
    title: "Live Cohort Intelligence",
    body: "Surfaces real-time cohort shifts, outcome risk signals, and validation diagnostics.",
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
          <img src="/images/j2.png" alt="ILAY avatar" className="landing-logo" />
          <h1 className="landing-title">ILAY</h1>
        </div>

        <p className="landing-tagline">AI-Powered Clinical Risk Intelligence</p>

        <div className="landing-value-grid">
          {VALUE_CARDS.map((card) => (
            <article key={card.title} className="landing-value-card">
              <h2>{card.title}</h2>
              <p>{card.body}</p>
            </article>
          ))}
        </div>

        <button type="button" className="landing-cta" onClick={onEnter} aria-label="Launch ILAY dashboard">
          Launch Dashboard
        </button>
      </div>
    </section>
  );
}
