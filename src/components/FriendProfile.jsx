import {
  ArrowLeft,
  BookOpen,
  CalendarDays,
  Check,
  CircleHelp,
  Sparkles,
  TrendingUp,
  UsersRound,
} from "lucide-react";
import "./friend-profile.css";

const fullDate = (value) =>
  new Intl.DateTimeFormat("uk-UA", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));

export default function FriendProfile({ profile, onBack, children }) {
  const { friend, tests, attempts, average, best } = profile;

  return (
    <div className="friend-profile">
      <button className="profile-back" onClick={onBack}>
        <ArrowLeft size={17} /> До друзів
      </button>

      <section className="profile-hero">
        <div className="profile-hero-pattern" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <div className="profile-hero-top">
          <span className="profile-label">
            <UsersRound size={15} /> ПРОФІЛЬ ДРУГА
          </span>
          <span className="profile-confirmed">
            <Check size={14} /> У друзях
          </span>
        </div>
        <div className="profile-identity">
          <span className={`profile-avatar ${friend.tone || "blue"}`}>
            {friend.initials}
          </span>
          <div>
            <h1>{friend.name}</h1>
            <p>@{friend.username}</p>
          </div>
        </div>
        <p className="profile-hero-caption">
          Навчайтеся разом: проходьте тести друга й стежте за його прогресом.
        </p>
      </section>

      <div className="profile-stats">
        <div className="profile-stat">
          <span className="profile-stat-icon lilac">
            <TrendingUp size={21} />
          </span>
          <div>
            <span>Середній результат</span>
            <strong>{average}%</strong>
            <small>за всіма завершеними спробами</small>
          </div>
        </div>
        <div className="profile-stat">
          <span className="profile-stat-icon blue">
            <BookOpen size={21} />
          </span>
          <div>
            <span>Створено тестів</span>
            <strong>{tests.length}</strong>
            <small>доступні вам для проходження</small>
          </div>
        </div>
        <div className="profile-stat">
          <span className="profile-stat-icon apricot">
            <CircleHelp size={21} />
          </span>
          <div>
            <span>Завершено спроб</span>
            <strong>{attempts.length}</strong>
            <small>найкращий результат — {best}%</small>
          </div>
        </div>
      </div>

      <div className="profile-content-grid">
        <section className="profile-tests-section">
          <div className="profile-section-heading">
            <div>
              <span className="eyebrow">ПОДІЛИСЯ З ВАМИ</span>
              <h2>Тести друга</h2>
            </div>
            <span className="profile-count">{tests.length} тестів</span>
          </div>
          {tests.length ? (
            <div className="profile-test-grid">{children}</div>
          ) : (
            <div className="profile-empty">
              <span>
                <BookOpen size={25} />
              </span>
              <h3>Тестів поки немає</h3>
              <p>Коли друг створить тест, він з’явиться тут.</p>
            </div>
          )}
          <div className="profile-hint">
            <Sparkles size={19} />
            <span>
              Результат вашого проходження збережеться у вашій історії.
            </span>
          </div>
        </section>

        <aside className="profile-results-section">
          <div className="profile-results-header">
            <div>
              <span className="eyebrow">ПРОГРЕС</span>
              <h2>Результати друга</h2>
            </div>
            <span className="profile-results-icon">
              <TrendingUp size={20} />
            </span>
          </div>
          {attempts.length ? (
            <div className="profile-results-list">
              {attempts.map((attempt) => (
                <div className="profile-result-row" key={attempt.id}>
                  <span
                    className={`profile-result-score ${attempt.score >= 80 ? "high" : attempt.score >= 60 ? "medium" : "low"}`}
                  >
                    {attempt.score}%
                  </span>
                  <div>
                    <strong>{attempt.testTitle}</strong>
                    <span>
                      <CalendarDays size={13} /> {fullDate(attempt.completedAt)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="profile-results-empty">
              <TrendingUp size={26} />
              <p>Завершених спроб поки немає.</p>
            </div>
          )}
          <p className="profile-results-note">
            Середній бал обчислено за всіма завершеними спробами друга.
          </p>
        </aside>
      </div>
    </div>
  );
}
