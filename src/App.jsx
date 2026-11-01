import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Bell,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  Heart,
  Home,
  Layers3,
  LogOut,
  Menu,
  Plus,
  ShieldCheck,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  TrendingUp,
  UploadCloud,
  UserRoundPlus,
  UsersRound,
  X,
} from "lucide-react";
import { api } from "./lib/api";
import { resetData } from "./mocks/data";
import FriendProfile from "./components/FriendProfile";
import "./studio-theme.css";

const nav = [
  ["dashboard", "Головна", Home],
  ["tests", "Мої тести", BookOpen],
  ["friends", "Друзі", UsersRound],
  ["history", "Історія", BarChart3],
];
const date = (value) =>
  new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "short" }).format(
    new Date(value),
  );
const longDate = (value) =>
  new Intl.DateTimeFormat("uk-UA", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
function Avatar({ initials, tone = "blue", small = false }) {
  return (
    <span className={`avatar ${tone} ${small ? "small" : ""}`}>{initials}</span>
  );
}
function Button({ children, icon: Icon, variant = "primary", ...props }) {
  return (
    <button className={`btn ${variant}`} {...props}>
      {Icon && <Icon size={18} />} {children}
    </button>
  );
}
function Empty({ title, text, action }) {
  return (
    <div className="empty">
      <span>
        <BookOpen size={27} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function TestCard({ test, onStart, onFavorite, onEdit, onDelete, own }) {
  return (
    <article className="test-card">
      <div className={`test-art ${test.accent}`}>
        <span className="art-circle circle-one" />
        <span className="art-circle circle-two" />
        <span className="art-symbol">
          <Layers3 size={29} />
        </span>
        <button
          className={`heart ${test.favorite ? "active" : ""}`}
          onClick={() => onFavorite(test.id)}
          aria-label={test.favorite ? "Прибрати з вибраного" : "У вибране"}
        >
          <Heart size={19} fill={test.favorite ? "currentColor" : "none"} />
        </button>
      </div>
      <div className="test-body">
        <div className="test-kicker">
          {test.subject}
          <span /> {test.difficulty}
        </div>
        <h3>{test.title}</h3>
        <p>{test.description}</p>
        <div className="test-meta">
          <span>
            <CircleHelp size={15} /> {test.questionCount} питань
          </span>
          <span>
            <Clock3 size={15} /> ~{test.duration} хв
          </span>
        </div>
        <div className="test-footer">
          <div className="owner">
            <Avatar
              initials={
                own
                  ? "ДС"
                  : test.ownerName
                      .split(" ")
                      .map((s) => s[0])
                      .join("")
              }
              tone={test.accent}
              small
            />
            {test.ownerName}
          </div>
          <div className="card-actions">
            {own && (
              <>
                <button title="Редагувати" onClick={() => onEdit(test)}>
                  <Settings2 size={17} />
                </button>
                <button title="Видалити" onClick={() => onDelete(test)}>
                  <Trash2 size={17} />
                </button>
              </>
            )}
            <button className="play" onClick={() => onStart(test)}>
              Почати <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
function AccountProfile({ data, go }) {
  const account = window.__FORMA_ACCOUNT__;
  const sessions = window.__FORMA_SESSIONS__;
  const ownTests = data.tests.filter((test) => String(test.ownerId) === String(account.id)).length;
  return (
    <section className="account-profile">
      <div className="page-head">
        <div>
          <span className="eyebrow">ВАШ ПРОСТІР У FORMA</span>
          <h1>Мій профіль</h1>
          <p>Навчання й безпека акаунта в одному місці.</p>
        </div>
      </div>
      <div className="account-hero">
        <Avatar initials={data.user.initials} />
        <div>
          <h2>{data.user.name}</h2>
          <p>{account.email}</p>
        </div>
        <span className="account-role">{account.role === "admin" ? "Адміністратор" : "Користувач"}</span>
      </div>
      <div className="account-card account-personal">
        <div className="account-personal-head">
          <div>
            <span className="account-card-label">ВАШІ ДАНІ</span>
            <h3>Особистий профіль</h3>
          </div>
          <a className="account-action" href="/account/settings">Редагувати профіль <ArrowRight size={17} /></a>
        </div>
        <div className="account-personal-grid">
          <div><span>Логін для входу</span><strong>{account.username || "Ще не створено"}</strong></div>
          <div><span>Дата народження</span><strong>{account.birth_date ? new Date(`${account.birth_date}T00:00:00`).toLocaleDateString("uk-UA") : "Не вказано"}</strong></div>
          <div className="account-bio"><span>Про себе</span><strong>{account.bio || "Можете додати кілька слів про себе"}</strong></div>
        </div>
      </div>
      <div className="account-grid">
        <div className="account-card">
          <span className="account-card-label">НАВЧАННЯ</span>
          <h3>Мій прогрес</h3>
          <div className="account-metrics">
            <div><strong>{ownTests}</strong><span>моїх тестів</span></div>
            <div><strong>{data.attempts.length}</strong><span>проходжень</span></div>
          </div>
          <button className="account-action" onClick={() => go("tests")}>Переглянути тести <ArrowRight size={17} /></button>
        </div>
        <div className="account-card">
          <span className="account-card-label"><ShieldCheck size={15} /> БЕЗПЕКА</span>
          <h3>Захист акаунта</h3>
          <div className="account-status"><span>Електронна пошта</span><strong>{account.active ? "Підтверджена" : "Очікує підтвердження"}</strong></div>
          <div className="account-status"><span>Двофакторний вхід</span><strong>{account.totp_enabled ? "Увімкнено" : "Вимкнено"}</strong></div>
          <div className="account-status"><span>Підключення Google-акаунта</span><strong>{account.google_connected ? "Підключено" : "Не підключено"}</strong></div>
          <div className="account-links">
            {!account.totp_enabled && <a className="account-action" href="/2fa/setup">Налаштувати 2FA <ArrowRight size={17} /></a>}
            {account.totp_enabled && <a className="account-action" href="/2fa/disable">Керувати 2FA <ArrowRight size={17} /></a>}
            {account.has_password && <form action="/forgot" method="post"><input type="hidden" name="csrf" value={window.__FORMA_CSRF__} /><button className="account-action" type="submit">Змінити пароль через email <ArrowRight size={17} /></button></form>}
            {!account.google_connected && account.google_available && <a className="account-action" href="/google/link/start">Підключити Google-акаунт <ArrowRight size={17} /></a>}
          </div>
          {!account.google_connected && !account.google_available && <p className="account-hint">Підключення Google стане доступним після налаштування Google OAuth.</p>}
        </div>
      </div>
      <div className="account-card account-sessions">
        <div className="account-sessions-head">
          <div>
            <span className="account-card-label"><ShieldCheck size={15} /> КОНТРОЛЬ ДОСТУПУ</span>
            <h3>Активні сеанси</h3>
            <p>Браузери, у яких зараз відкритий ваш акаунт.</p>
          </div>
          <span className="account-session-count">{sessions?.length ?? "—"}</span>
        </div>
        {sessions === null && <p className="account-session-error" role="alert">Сервер облікових записів ще працює зі старою версією. Перезапустіть backend, потім натисніть «Оновити список».</p>}
        {new URLSearchParams(window.location.search).get("sessions") === "revoked" && <p className="account-session-notice" role="status">Інші сеанси завершено. Поточний браузер залишився в акаунті.</p>}
        <div className="account-session-list">
          {(sessions ?? []).map((item, index) => (
            <div className="account-session" key={`${item.created_at}-${index}`}>
              <div className="account-session-icon"><ShieldCheck size={20} /></div>
              <div className="account-session-info">
                <div className="account-session-title"><strong>{item.device}</strong>{item.current && <span className="account-session-current">Цей пристрій</span>}</div>
                <p>{item.local_pc_ip ? "IP ПК" : item.ip === "127.0.0.1" || item.ip === "::1" ? "Локальна адреса" : "IP"}: {item.display_ip ?? item.ip} · Вхід: {new Date(item.created_at * 1000).toLocaleString("uk-UA")}</p>
                <small>Остання активність: {new Date(item.last_seen_at * 1000).toLocaleString("uk-UA")}</small>
              </div>
            </div>
          ))}
        </div>
        <div className="account-sessions-actions">
          <button type="button" onClick={() => window.location.reload()}>Оновити список</button>
          <form action="/sessions/revoke-others" method="post">
            <input type="hidden" name="csrf" value={window.__FORMA_CSRF__} />
            <button type="submit" disabled={!sessions || sessions.length < 2}>Завершити інші сеанси</button>
          </form>
        </div>
        <p className="account-hint">Для локальних сеансів показано IPv4-адресу ПК на активному мережевому маршруті. Адреса з’єднання 127.0.0.1 залишається у журналі сервера.</p>
      </div>
      <div className="account-card account-recent">
        <span className="account-card-label">БЕЗПЕКА АКАУНТА</span>
        <h3>Останні події</h3>
        {(window.__FORMA_EVENTS__ ?? []).length ? (
          <ul>
            {window.__FORMA_EVENTS__.map((event, index) => (
              <li key={`${event.at}-${index}`}>
                <span>{event.event}</span>
                <small>{new Date(event.at * 1000).toLocaleString("uk-UA")}{event.ip ? ` · ${event.ip}` : ""}</small>
              </li>
            ))}
          </ul>
        ) : <p>Подій поки немає.</p>}
      </div>
      <form className="account-logout" action="/logout" method="post">
        <input type="hidden" name="csrf" value={window.__FORMA_CSRF__} />
        <button type="submit"><LogOut size={17} /> Вийти з акаунта</button>
      </form>
    </section>
  );
}
function Dashboard({ data, go, cardProps }) {
  const last = data.attempts[0];
  return (
    <>
      <div className="welcome">
        <div>
          <span className="eyebrow">ВАШ ПРОСТІР ДЛЯ НАВЧАННЯ</span>
          <h1>
            Привіт, {data.user.name.split(" ")[0]} <span>✳</span>
          </h1>
          <p>Сьогодні хороший день, щоб дізнатися щось нове.</p>
        </div>
        <span className="today">
          <i /> {longDate(new Date())}
        </span>
      </div>
      <div className="hero">
        <div className="hero-text">
          <span className="hero-label">
            <Sparkles size={16} /> РОЗУМНЕ НАВЧАННЯ
          </span>
          <h2>
            Нові знання
            <br />
            починаються тут.
          </h2>
          <p>
            Створіть тест із власного матеріалу та перевірте, що вже знаєте.
          </p>
          <Button variant="white" icon={Plus} onClick={() => go("create")}>
            Створити тест
          </Button>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-a" />
          <div className="orbit orbit-b" />
          <div className="float float-a">
            <span>01</span>
            <Check size={22} />
          </div>
          <div className="float float-b">
            <span>?</span>
            <i />
          </div>
          <div className="float float-c">
            <span>А</span>
            <span>Б</span>
            <span>В</span>
          </div>
          <b>✦</b>
        </div>
      </div>
      <div className="stats">
        <div className="stat">
          <span className="stat-icon violet">
            <TrendingUp size={23} />
          </span>
          <div>
            <span>Середній результат</span>
            <strong>{data.average}%</strong>
            <small>за всіма завершеними спробами</small>
          </div>
        </div>
        <div className="stat">
          <span className="stat-icon blue">
            <BookOpen size={23} />
          </span>
          <div>
            <span>Мої тести</span>
            <strong>{data.ownCount}</strong>
            <small>створено вами</small>
          </div>
        </div>
        <div className="stat">
          <span className="stat-icon peach">
            <CheckCircle2 size={23} />
          </span>
          <div>
            <span>Пройдено тестів</span>
            <strong>{data.attempts.length}</strong>
            <small>усі завершені спроби</small>
          </div>
        </div>
      </div>
      <div className="dash-bottom">
        <div>
          <div className="section-title">
            <div>
              <span className="eyebrow">ДЛЯ ВАС</span>
              <h2>Нещодавні тести</h2>
            </div>
            <button className="link" onClick={() => go("tests")}>
              Переглянути всі <ArrowRight size={17} />
            </button>
          </div>
          <div className="test-grid">
            {data.tests.slice(0, 3).map((t) => (
              <TestCard
                key={t.id}
                test={t}
                own={t.ownerId === data.user.id}
                {...cardProps}
              />
            ))}
          </div>
        </div>
        <aside className="activity">
          <span className="eyebrow">ВАША АКТИВНІСТЬ</span>
          <span className="activity-icon">
            <BarChart3 size={21} />
          </span>
          <h3>Тримайте темп</h3>
          <p>Навчання маленькими кроками дає великий результат.</p>
          <div className="chart">
            {data.attempts
              .slice(0, 5)
              .reverse()
              .map((a, i) => (
                <div key={a.id}>
                  <span
                    className={i === 4 ? "selected" : ""}
                    style={{ height: `${Math.max(22, a.score)}%` }}
                  />
                  <small>{date(a.completedAt)}</small>
                </div>
              ))}
          </div>
          <div className="last-score">
            <span>Останній результат</span>
            <strong>{last?.score || 0}%</strong>
            <small>
              {data.tests.find((t) => t.id === last?.testId)?.title ||
                "Ще немає проходжень"}
            </small>
          </div>
          <button className="link" onClick={() => go("history")}>
            Історія проходжень <ArrowRight size={17} />
          </button>
        </aside>
      </div>
    </>
  );
}
function Tests({ data, tab, setTab, search, setSearch, go, cardProps }) {
  const list = useMemo(
    () =>
      data.tests
        .filter((t) =>
          tab === "own"
            ? t.ownerId === data.user.id
            : tab === "friends"
              ? t.ownerId !== data.user.id
              : t.favorite,
        )
        .filter((t) =>
          `${t.title} ${t.subject} ${t.ownerName}`
            .toLowerCase()
            .includes(search.toLowerCase()),
        ),
    [data, tab, search],
  );
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">ВАША БІБЛІОТЕКА</span>
          <h1>Тести</h1>
          <p>Усе для навчання в одному місці.</p>
        </div>
        <Button icon={Plus} onClick={() => go("create")}>
          Створити тест
        </Button>
      </div>
      <div className="library">
        <div className="toolbar">
          <div className="tabs">
            {[
              ["own", "Мої тести"],
              ["friends", "Тести друзів"],
              ["favorites", "Вибране"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {label}
                {id === "favorites" && <span>{data.favoritesCount}</span>}
              </button>
            ))}
          </div>
          <label className="search">
            <Search size={18} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Пошук тестів"
            />
          </label>
        </div>
        {list.length ? (
          <div className="test-grid library-grid">
            {list.map((t) => (
              <TestCard
                key={t.id}
                test={t}
                own={t.ownerId === data.user.id}
                {...cardProps}
              />
            ))}
          </div>
        ) : (
          <Empty
            title="Тестів поки немає"
            text={
              search
                ? "Спробуйте інший пошуковий запит."
                : tab === "favorites"
                  ? "Позначте тест серцем, щоб знайти його тут."
                  : "Створіть перший тест із навчального матеріалу."
            }
            action={
              !search &&
              tab === "own" && (
                <Button icon={Plus} onClick={() => go("create")}>
                  Створити тест
                </Button>
              )
            }
          />
        )}
      </div>
    </>
  );
}
function Create({ data, onCreate, go, busy }) {
  const [form, setForm] = useState({
    title: "",
    subject: "",
    material: "",
    difficulty: "Адаптивна",
    questionCount: 5,
  });
  const [errors, setErrors] = useState({});
  const update = (k, v) => {
    setForm({ ...form, [k]: v });
    setErrors({ ...errors, [k]: "" });
  };
  const predicted =
    data.average >= 80
      ? "складний"
      : data.average >= 60
        ? "середній"
        : "легкий";
  const submit = (e) => {
    e.preventDefault();
    const err = {};
    if (!form.title.trim()) err.title = "Укажіть назву тесту.";
    if (form.material.trim().length < 40)
      err.material = "Додайте щонайменше 40 символів.";
    setErrors(err);
    if (!Object.keys(err).length) onCreate(form);
  };
  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".txt") || file.size > 2e6) {
      setErrors({ ...errors, material: "Доступний файл .txt до 2 МБ." });
      return;
    }
    update("material", await file.text());
  };
  return (
    <>
      <div className="page-head">
        <div>
          <button className="back" onClick={() => go("tests")}>
            <ArrowLeft size={16} /> До тестів
          </button>
          <h1>Новий тест</h1>
          <p>Перетворіть свій матеріал на коротку перевірку знань.</p>
        </div>
        <span className="step">Крок 1 із 1</span>
      </div>
      <form className="create-layout" onSubmit={submit}>
        <div className="form-card">
          <div className="form-head">
            <span>
              <FileText size={22} />
            </span>
            <div>
              <h2>Основна інформація</h2>
              <p>Почнімо з теми вашого тесту.</p>
            </div>
          </div>
          <label className="field">
            <span>
              Назва тесту <em>*</em>
            </span>
            <input
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
              placeholder="Наприклад, Основи баз даних"
              maxLength="80"
            />
            {errors.title && (
              <small className="error-text">{errors.title}</small>
            )}
          </label>
          <label className="field">
            <span>Предмет</span>
            <input
              value={form.subject}
              onChange={(e) => update("subject", e.target.value)}
              placeholder="Наприклад, Інформатика"
            />
          </label>
          <label className="field">
            <span>
              Навчальний матеріал <em>*</em>
            </span>
            <textarea
              rows="8"
              value={form.material}
              onChange={(e) => update("material", e.target.value)}
              placeholder="Вставте конспект, уривок лекції або текст, за яким потрібно створити запитання..."
            />
            <div className="field-foot">
              <small className={errors.material ? "error-text" : ""}>
                {errors.material ||
                  "Мінімум 40 символів. Демо створює прості запитання з речень."}
              </small>
              <small>{form.material.length} символів</small>
            </div>
          </label>
          <label className="upload">
            <UploadCloud size={20} />
            <span>
              Завантажити текстовий файл <small>TXT, до 2 МБ</small>
            </span>
            <input type="file" accept=".txt,text/plain" onChange={upload} />
          </label>
        </div>
        <div className="form-card">
          <div className="form-head">
            <span className="blue">
              <Settings2 size={22} />
            </span>
            <div>
              <h2>Налаштування</h2>
              <p>Виберіть складність і кількість запитань.</p>
            </div>
          </div>
          <div className="two-fields">
            <label className="field">
              <span>Складність</span>
              <div className="select">
                <select
                  value={form.difficulty}
                  onChange={(e) => update("difficulty", e.target.value)}
                >
                  {["Адаптивна", "Легкий", "Середній", "Складний"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
                <ChevronDown size={18} />
              </div>
            </label>
            <label className="field">
              <span>Кількість питань</span>
              <div className="select">
                <select
                  value={form.questionCount}
                  onChange={(e) => update("questionCount", e.target.value)}
                >
                  {[3, 5, 8, 10, 15, 20].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
                <ChevronDown size={18} />
              </div>
            </label>
          </div>
          <div className="adaptive">
            <Sparkles size={20} />
            <p>
              <strong>Адаптивна складність</strong>
              <br />
              За середнім результатом {data.average}% система запропонує{" "}
              {predicted} рівень.
            </p>
          </div>
        </div>
        <div className="form-actions">
          <Button variant="ghost" type="button" onClick={() => go("tests")}>
            Скасувати
          </Button>
          <Button icon={Sparkles} disabled={busy}>
            {busy ? "Створення…" : "Створити тест"}
          </Button>
        </div>
      </form>
    </>
  );
}
function Quiz({ test, onFinish, onClose, busy }) {
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const q = test.questions[index];
  return (
    <div className="quiz">
      <div className="quiz-top">
        <button className="back" onClick={onClose}>
          <X size={19} /> Вийти з тесту
        </button>
        <strong>{test.title}</strong>
        <span>
          {index + 1} / {test.questions.length}
        </span>
      </div>
      <div className="quiz-content">
        <div className="progress">
          <span
            style={{ width: `${((index + 1) / test.questions.length) * 100}%` }}
          />
        </div>
        <div className="quiz-meta">
          <span>ПИТАННЯ {String(index + 1).padStart(2, "0")}</span>
          <span>{test.difficulty} рівень</span>
        </div>
        <h1>{q.text}</h1>
        <p>Виберіть одну правильну відповідь</p>
        <div className="options">
          {q.options.map((o, i) => (
            <button
              key={i}
              className={answers[index] === i ? "selected" : ""}
              onClick={() => setAnswers({ ...answers, [index]: i })}
            >
              <span>{String.fromCharCode(65 + i)}</span>
              {o}
              {answers[index] === i && <CheckCircle2 size={19} />}
            </button>
          ))}
        </div>
        <div className="quiz-actions">
          <Button
            variant="ghost"
            icon={ChevronLeft}
            disabled={index === 0}
            onClick={() => setIndex(index - 1)}
          >
            Назад
          </Button>
          {index < test.questions.length - 1 ? (
            <Button
              disabled={answers[index] === undefined}
              onClick={() => setIndex(index + 1)}
            >
              Далі <ChevronRight size={17} />
            </Button>
          ) : (
            <Button
              disabled={
                Object.keys(answers).length !== test.questions.length || busy
              }
              onClick={() => onFinish(test.id, answers)}
            >
              {busy ? "Збереження…" : "Завершити тест"} <ArrowRight size={17} />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
function Result({ result, test, go, retry }) {
  return (
    <div className="result">
      <span className="result-spark">✦</span>
      <div className="result-circle">
        <strong>{result.score}%</strong>
        <span>результат</span>
      </div>
      <span className="eyebrow">ТЕСТ ЗАВЕРШЕНО</span>
      <h1>
        {result.score >= 80
          ? "Чудова робота!"
          : result.score >= 60
            ? "Хороший результат!"
            : "Продовжуйте навчатися!"}
      </h1>
      <p>
        Ви правильно відповіли на {result.correct} із {result.total} питань
        тесту «{test.title}».
      </p>
      <div>
        <Button variant="ghost" onClick={() => go("history")}>
          Переглянути історію
        </Button>
        <Button onClick={retry}>
          Пройти ще раз <ArrowRight size={17} />
        </Button>
      </div>
    </div>
  );
}
function History({ data, onOpen }) {
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">ВАШ ПРОГРЕС</span>
          <h1>Історія проходжень</h1>
          <p>Кожна завершена спроба зберігається окремо.</p>
        </div>
        <span className="summary">
          <TrendingUp size={17} /> Середній бал {data.average}%
        </span>
      </div>
      <div className="history-layout">
        <div className="history-card">
          <div className="history-head">
            <h2>Усі спроби</h2>
            <span>{data.attempts.length} записів</span>
          </div>
          {data.attempts.length ? (
            data.attempts.map((a) => {
              const t = data.tests.find((t) => t.id === a.testId);
              return (
                <button
                  type="button"
                  className="history-row"
                  key={a.id}
                  onClick={() => onOpen(a.id)}
                  aria-label={`Переглянути спробу: ${t?.title || "Видалений тест"}, ${a.score}%`}
                >
                  <span className={`history-icon ${t?.accent || "blue"}`}>
                    <BookOpen size={20} />
                  </span>
                  <div>
                    <strong>{t?.title || "Видалений тест"}</strong>
                    <span>
                      {t?.subject || "Тест"} · {longDate(a.completedAt)}
                    </span>
                  </div>
                  <b
                    className={`score ${a.score >= 80 ? "high" : a.score >= 60 ? "medium" : "low"}`}
                  >
                    {a.score}%
                  </b>
                  <ChevronRight size={18} />
                </button>
              );
            })
          ) : (
            <Empty
              title="Історія порожня"
              text="Пройдіть тест, і результат з’явиться тут."
            />
          )}
        </div>
        <aside className="insight">
          <span className="stat-icon violet">
            <BarChart3 size={24} />
          </span>
          <span className="eyebrow">КОРОТКО ПРО ПРОГРЕС</span>
          <h3>{data.average}%</h3>
          <p>
            Середній відсоток за всіма {data.attempts.length} завершеними
            спробами.
          </p>
          <div>
            <span>Найкраща спроба</span>
            <strong>
              {Math.max(0, ...data.attempts.map((a) => a.score))}%
            </strong>
          </div>
          <div>
            <span>Пройдено разів</span>
            <strong>{data.attempts.length}</strong>
          </div>
        </aside>
      </div>
    </>
  );
}
function AttemptDetails({ data, attemptId, go }) {
  const attempt = data.attempts.find((item) => item.id === attemptId);
  if (!attempt) {
    return (
      <div className="attempt-details">
        <Button variant="ghost" onClick={() => go("history")} icon={ArrowLeft}>
          До історії
        </Button>
        <Empty title="Спробу не знайдено" text="Цей запис більше не доступний." />
      </div>
    );
  }
  const test = data.tests.find((item) => item.id === attempt.testId);
  const review = attempt.review;
  return (
    <div className="attempt-details">
      <button className="back" onClick={() => go("history")}>
        <ArrowLeft size={18} /> До історії
      </button>
      <div className="page-head">
        <div>
          <span className="eyebrow">ДЕТАЛІ СПРОБИ</span>
          <h1>{test?.title || "Видалений тест"}</h1>
          <p>Завершено {longDate(attempt.completedAt)}</p>
        </div>
      </div>
      <section className="attempt-summary">
        <span className={`score ${attempt.score >= 80 ? "high" : attempt.score >= 60 ? "medium" : "low"}`}>
          {attempt.score}%
        </span>
        <div>
          <strong>Результат проходження</strong>
          <p>{attempt.correct != null && attempt.total != null
            ? `Правильних відповідей: ${attempt.correct} із ${attempt.total}.`
            : "Для цієї старої спроби збережено лише загальний відсоток."}</p>
        </div>
      </section>
      {Array.isArray(review) && review.length > 0 ? (
        <section className="attempt-review">
          <h2>Відповіді на питання</h2>
          {review.map((question, index) => (
            <article className="attempt-question" key={index}>
              <span>Питання {index + 1}</span>
              <h3>{question.text}</h3>
              <p>Ваша відповідь: <strong>{question.selected == null ? "Не вибрано" : question.options[question.selected] ?? "Недоступна"}</strong></p>
              <p>Правильна відповідь: <strong>{question.options[question.correct] ?? "Недоступна"}</strong></p>
              <span className={question.selected === question.correct ? "attempt-correct" : "attempt-incorrect"}>
                {question.selected === question.correct ? "Правильно" : "Помилка"}
              </span>
            </article>
          ))}
        </section>
      ) : (
        <p className="attempt-legacy-note">Відповіді для цієї спроби не зберігалися. Детальний перегляд буде доступний для нових проходжень.</p>
      )}
    </div>
  );
}
function Friends({ friends, requests, reload, notify, busy, setBusy, onOpen }) {
  const [username, setUsername] = useState("");
  async function send(e) {
    e.preventDefault();
    try {
      setBusy(true);
      await api.friendRequest(username);
      setUsername("");
      await reload();
      notify("Запит на дружбу надіслано.");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function respond(id, action) {
    try {
      setBusy(true);
      await api.respondRequest(id, action);
      await reload();
      notify(action === "accept" ? "Запит прийнято." : "Запит відхилено.");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">НАВЧАЙТЕСЯ РАЗОМ</span>
          <h1>Друзі</h1>
          <p>Діліться тестами та підтримуйте одне одного.</p>
        </div>
        <span className="summary">
          <UsersRound size={17} /> {friends.length} друзів
        </span>
      </div>
      <div className="friends-layout">
        <div>
          <div className="friends-card">
            <h2>Мої друзі</h2>
            {friends.map((f) => (
              <button
                className="person person-button"
                key={f.id}
                onClick={() => onOpen(f.id)}
                aria-label={`Відкрити профіль ${f.name}`}
              >
                <Avatar initials={f.initials} tone={f.tone} />
                <div>
                  <strong>{f.name}</strong>
                  <span>@{f.username}</span>
                </div>
                <span className="friend-status">
                  <i /> Друг
                </span>
                <ChevronRight size={18} />
              </button>
            ))}
          </div>
          <div className="friends-card">
            <h2>Запити в друзі</h2>
            {requests.length ? (
              requests.map((r) => (
                <div className="person" key={r.id}>
                  <Avatar initials={r.initials} tone={r.tone} />
                  <div>
                    <strong>{r.name}</strong>
                    <span>
                      @{r.username} ·{" "}
                      {r.direction === "incoming"
                        ? "хоче додати вас"
                        : "очікує підтвердження"}
                    </span>
                  </div>
                  {r.direction === "incoming" ? (
                    <div className="request-actions">
                      <button
                        onClick={() => respond(r.id, "reject")}
                        disabled={busy}
                        title="Відхилити"
                      >
                        <X size={18} />
                      </button>
                      <button
                        className="accept"
                        onClick={() => respond(r.id, "accept")}
                        disabled={busy}
                        title="Прийняти"
                      >
                        <Check size={18} />
                      </button>
                    </div>
                  ) : (
                    <span className="pending">Очікує</span>
                  )}
                </div>
              ))
            ) : (
              <p className="no-requests">Нових запитів немає.</p>
            )}
          </div>
        </div>
        <aside className="add-friend">
          <span className="add-icon">
            <UserRoundPlus size={24} />
          </span>
          <h2>Додати друга</h2>
          <p>Введіть ім’я користувача, щоб надіслати запит.</p>
          <form onSubmit={send}>
            <label className="field">
              <span>Ім’я користувача</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Наприклад, maria.k"
              />
            </label>
            <Button icon={Plus} disabled={busy}>
              Надіслати запит
            </Button>
          </form>
          <small>Тести друзів доступні після підтвердження запиту.</small>
        </aside>
      </div>
    </>
  );
}
function Modal({ test, mode, onClose, onSave, onDelete, busy }) {
  const [form, setForm] = useState({
    title: test.title,
    subject: test.subject,
    description: test.description,
  });
  return (
    <div className="backdrop" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{mode === "edit" ? "Редагувати тест" : "Видалити тест?"}</h2>
          <button onClick={onClose}>
            <X size={21} />
          </button>
        </div>
        {mode === "edit" ? (
          <>
            <label className="field">
              <span>Назва тесту</span>
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Предмет</span>
              <input
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Опис</span>
              <textarea
                rows="3"
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </label>
          </>
        ) : (
          <p>
            «{test.title}» буде прибрано з бібліотеки. Історія ваших спроб
            залишиться.
          </p>
        )}
        <div className="modal-actions">
          <Button variant="ghost" onClick={onClose}>
            Скасувати
          </Button>
          <Button
            variant={mode === "delete" ? "danger" : "primary"}
            disabled={busy || (mode === "edit" && !form.title.trim())}
            onClick={() =>
              mode === "edit" ? onSave(test.id, form) : onDelete(test.id)
            }
          >
            {mode === "edit" ? "Зберегти" : "Видалити"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState(new URLSearchParams(window.location.search).get("view") === "profile" ? "profile" : "dashboard"),
    [data, setData] = useState(null),
    [people, setPeople] = useState({ friends: [], requests: [] }),
    [friendProfile, setFriendProfile] = useState(null),
    [tab, setTab] = useState("own"),
    [search, setSearch] = useState(""),
    [quiz, setQuiz] = useState(null),
    [result, setResult] = useState(null),
    [selectedAttemptId, setSelectedAttemptId] = useState(null),
    [modal, setModal] = useState(null),
    [busy, setBusy] = useState(false),
    [toast, setToast] = useState(null),
    [menu, setMenu] = useState(false);
  async function reload() {
    const [a, b] = await Promise.all([api.overview(), api.friends()]);
    setData(a);
    setPeople(b);
  }
  useEffect(() => {
    reload().catch((e) => notify(e.message, "error"));
  }, []);
  function notify(message, type = "success") {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }
  function go(p) {
    setPage(p);
    setMenu(false);
    window.history.replaceState(null, "", p === "profile" ? "/?view=profile" : "/");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function openFriend(id) {
    setFriendProfile(null);
    go("friendProfile");
    try {
      setFriendProfile(await api.friendProfile(id));
    } catch (e) {
      notify(e.message, "error");
      go("friends");
    }
  }
  async function run(task, success) {
    try {
      setBusy(true);
      await task();
      await reload();
      if (success) notify(success);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  function start(t) {
    setQuiz(t);
    setResult(null);
    go("quiz");
  }
  async function finish(id, answers) {
    try {
      setBusy(true);
      const r = await api.attempt({ testId: id, answers });
      await reload();
      setResult(r);
      go("result");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function create(form) {
    try {
      setBusy(true);
      await api.createTest(form);
      await reload();
      setTab("own");
      go("tests");
      notify("Тест створено в демо-режимі.");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function save(id, form) {
    await run(() => api.updateTest(id, form), "Зміни збережено.");
    setModal(null);
  }
  async function remove(id) {
    await run(() => api.deleteTest(id), "Тест видалено.");
    setModal(null);
  }
  function restore() {
    resetData();
    reload();
    setFriendProfile(null);
    go("dashboard");
    notify("Демонстраційні дані відновлено.");
  }
  const cardProps = {
    onStart: start,
    onFavorite: (id) => run(() => api.favorites(id)),
    onEdit: (test) => setModal({ test, mode: "edit" }),
    onDelete: (test) => setModal({ test, mode: "delete" }),
  };
  if (!data)
    return (
      <div className="loading">
        <span className="brand-mark">
          <Sparkles size={24} />
        </span>{" "}
        Завантаження Forma…
      </div>
    );
  const simple = ["quiz", "result"].includes(page);
  return (
    <div className={`app studio-theme ${simple ? "simple-app" : ""}`}>
      {!simple && (
        <>
          <div
            className={`overlay ${menu ? "show" : ""}`}
            onClick={() => setMenu(false)}
          />
          <aside className={`sidebar ${menu ? "open" : ""}`}>
            <button className="brand" onClick={() => go("dashboard")}>
              <span className="brand-mark">
                <Sparkles size={22} />
              </span>
              <span>
                forma<b>.</b>
              </span>
            </button>
            <div className="nav-group">
              <span className="side-label">ОСНОВНЕ</span>
              <nav>
                {nav.map(([id, label, Icon]) => (
                  <button
                    key={id}
                    className={`nav-item ${page === id || (page === "friendProfile" && id === "friends") ? "active" : ""}`}
                    onClick={() => go(id)}
                  >
                    <Icon size={20} />
                    <span>{label}</span>
                    {id === "friends" &&
                      people.requests.some(
                        (r) => r.direction === "incoming",
                      ) && <i />}
                  </button>
                ))}
              </nav>
            </div>
            <div className="side-bottom">
              <span className="side-label">ІНСТРУМЕНТИ</span>
              <button className={`nav-item ${page === "profile" ? "active" : ""}`} onClick={() => go("profile")}>
                <ShieldCheck size={20} /> Мій профіль
              </button>
              {window.__FORMA_ACCOUNT__?.role === "admin" && (
                <a className="nav-item account-link" href="/admin">
                  <UsersRound size={20} /> Адміністрування
                </a>
              )}
              <button className="nav-item" onClick={restore}>
                <Settings2 size={20} /> Скинути демо
              </button>
              <div className="side-promo">
                <span>
                  <Sparkles size={20} />
                </span>
                <strong>Навчайтесь у своєму темпі</strong>
                <p>Створюйте тести й відстежуйте прогрес щодня.</p>
                <button onClick={() => go("create")}>
                  Новий тест <ArrowRight size={16} />
                </button>
              </div>
              <button className="side-user account-user-button" onClick={() => go("profile")} aria-label="Відкрити мій профіль">
                <Avatar initials={data.user.initials} />
                <div>
                  <strong>{data.user.name}</strong>
                  <span>{window.__FORMA_ACCOUNT__?.role === "admin" ? "Адміністратор" : "Особистий простір"}</span>
                </div>
              </button>
            </div>
          </aside>
        </>
      )}
      <div className="main-area">
        {!simple && (
          <header className="topbar">
            <div>
              <button
                className="menu-button"
                onClick={() => setMenu(true)}
                aria-label="Відкрити меню"
              >
                <Menu size={22} />
              </button>
              <span className="breadcrumb">
                Простір <ChevronRight size={15} />{" "}
                <strong>
                  {
                    {
                      dashboard: "Головна",
                      tests: "Тести",
                      create: "Новий тест",
                      friends: "Друзі",
                      friendProfile:
                        friendProfile?.friend.name || "Профіль друга",
                      history: "Історія",
                      profile: "Мій профіль",
                      attemptDetails: "Деталі спроби",
                    }[page]
                  }
                </strong>
              </span>
            </div>
            <div className="top-actions">
              <span className="demo">
                <i /> Демо-режим
              </span>
              <button
                className="bell"
                onClick={() => go("friends")}
                title="Запити в друзі"
              >
                <Bell size={20} />
                {people.requests.some((r) => r.direction === "incoming") && (
                  <i />
                )}
              </button>
              <button className="account-avatar-button" onClick={() => go("profile")} aria-label="Мій профіль"><Avatar initials={data.user.initials} small /></button>
            </div>
          </header>
        )}
        <main className={simple ? "simple-main" : "content"}>
          {page === "dashboard" && (
            <Dashboard data={data} go={go} cardProps={cardProps} />
          )}
          {page === "profile" && <AccountProfile data={data} go={go} />}
          {page === "tests" && (
            <Tests
              data={data}
              tab={tab}
              setTab={setTab}
              search={search}
              setSearch={setSearch}
              go={go}
              cardProps={cardProps}
            />
          )}
          {page === "create" && (
            <Create data={data} onCreate={create} go={go} busy={busy} />
          )}
          {page === "quiz" && quiz && (
            <Quiz
              key={quiz.id}
              test={quiz}
              onFinish={finish}
              onClose={() => go("tests")}
              busy={busy}
            />
          )}
          {page === "result" && quiz && result && (
            <Result
              result={result}
              test={quiz}
              go={go}
              retry={() => start(quiz)}
            />
          )}
          {page === "history" && <History data={data} onOpen={(id) => { setSelectedAttemptId(id); go("attemptDetails"); }} />}
          {page === "attemptDetails" && <AttemptDetails data={data} attemptId={selectedAttemptId} go={go} />}
          {page === "friends" && (
            <Friends
              friends={people.friends}
              requests={people.requests}
              reload={reload}
              notify={notify}
              busy={busy}
              setBusy={setBusy}
              onOpen={openFriend}
            />
          )}
          {page === "friendProfile" &&
            (friendProfile ? (
              <FriendProfile
                profile={friendProfile}
                onBack={() => go("friends")}
              >
                {friendProfile.tests.map((test) => (
                  <TestCard
                    key={test.id}
                    test={
                      data.tests.find((item) => item.id === test.id) || test
                    }
                    own={false}
                    {...cardProps}
                  />
                ))}
              </FriendProfile>
            ) : (
              <div className="loading friend-loading">
                Завантаження профілю…
              </div>
            ))}
        </main>
      </div>
      {modal && (
        <Modal
          key={modal.test.id}
          test={modal.test}
          mode={modal.mode}
          onClose={() => setModal(null)}
          onSave={save}
          onDelete={remove}
          busy={busy}
        />
      )}
      {toast && (
        <div className={`toast ${toast.type}`}>
          <span>
            {toast.type === "error" ? <X size={18} /> : <Check size={18} />}
          </span>
          {toast.message}
        </div>
      )}
    </div>
  );
}
