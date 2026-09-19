import styles from "./page.module.css";

const projects = [
  {
    number: "01",
    title: "Facial Recognition System",
    description:
      "Computer vision and machine learning system for facial detection and recognition.",
    tags: ["Python", "Computer Vision", "Machine Learning"],
  },
  {
    number: "02",
    title: "Numerical Analysis",
    description:
      "Interactive numerical methods and scientific computing experiments with visualization.",
    tags: ["Python", "Numerical Methods", "Scientific Computing"],
  },
  {
    number: "03",
    title: "Bitcoin Analytics",
    description:
      "Market analytics and time-series forecasting platform for Bitcoin data.",
    tags: ["Python", "Time Series", "Data Engineering", "Machine Learning"],
  },
];

const capabilities = [
  "Python Development",
  "Machine Learning",
  "Data Engineering",
  "AI Automation",
  "APIs & Backend Systems",
  "Data Visualization",
];

export default function Home() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="#top" aria-label="GrekoLabs home">
          <span className={styles.brandMark} aria-hidden="true" />
          GrekoLabs
        </a>

        <nav className={styles.navigation} aria-label="Main navigation">
          <a href="#projects">Projects</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#about">About</a>
        </nav>
      </header>

      <main id="top">
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroGlow} aria-hidden="true" />
          <p className={styles.eyebrow}>Independent Technology Lab</p>
          <h1 id="hero-title">Building intelligent systems from data.</h1>
          <p className={styles.heroDescription}>
            GrekoLabs is an independent technology lab focused on data,
            machine learning, AI automation and intelligent applications.
          </p>
          <p className={styles.disciplines}>
            <span>Data</span>
            <span>AI</span>
            <span>Machine Learning</span>
            <span>Automation</span>
          </p>
          <div className={styles.heroActions}>
            <a className={styles.primaryButton} href="#projects">
              Explore Projects
              <span aria-hidden="true">↓</span>
            </a>
            <a
              className={styles.secondaryButton}
              href="https://github.com/GrekoLabs"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
              <span aria-hidden="true">↗</span>
            </a>
          </div>
        </section>

        <section
          className={styles.section}
          id="projects"
          aria-labelledby="projects-title"
        >
          <div className={styles.sectionHeading}>
            <p className={styles.sectionLabel}>Selected work</p>
            <h2 id="projects-title">Featured Projects</h2>
          </div>

          <div className={styles.projectGrid}>
            {projects.map((project) => (
              <article className={styles.projectCard} key={project.title}>
                <div className={styles.projectTopline}>
                  <span>{project.number}</span>
                  <span className={styles.projectStatus}>In development</span>
                </div>
                <h3>{project.title}</h3>
                <p className={styles.projectDescription}>
                  {project.description}
                </p>
                <ul className={styles.tagList} aria-label="Technologies">
                  {project.tags.map((tag) => (
                    <li key={tag}>{tag}</li>
                  ))}
                </ul>
                <button className={styles.projectLink} type="button" disabled>
                  View Project <span aria-hidden="true">↗</span>
                </button>
              </article>
            ))}
          </div>
        </section>

        <section
          className={`${styles.section} ${styles.capabilitiesSection}`}
          id="capabilities"
          aria-labelledby="capabilities-title"
        >
          <div className={styles.sectionHeading}>
            <p className={styles.sectionLabel}>Core disciplines</p>
            <h2 id="capabilities-title">Capabilities</h2>
          </div>

          <ul className={styles.capabilityGrid}>
            {capabilities.map((capability, index) => (
              <li key={capability}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {capability}
              </li>
            ))}
          </ul>
        </section>

        <section
          className={`${styles.section} ${styles.aboutSection}`}
          id="about"
          aria-labelledby="about-title"
        >
          <p className={styles.sectionLabel}>About the lab</p>
          <div className={styles.aboutContent}>
            <h2 id="about-title">Ideas become working systems.</h2>
            <p>
              GrekoLabs is where I build, test and publish technology projects
              focused on solving real problems with software, data and
              artificial intelligence.
            </p>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div>
          <p className={styles.footerBrand}>GrekoLabs</p>
          <p>Data · AI · Intelligent Systems</p>
        </div>
        <a
          href="https://github.com/GrekoLabs"
          target="_blank"
          rel="noreferrer"
        >
          GitHub <span aria-hidden="true">↗</span>
        </a>
      </footer>
    </div>
  );
}
