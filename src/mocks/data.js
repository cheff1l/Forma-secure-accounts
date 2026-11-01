const initial = {
  user: {
    id: "u1",
    name: "Денис Семкович",
    username: "denys",
    initials: "ДС",
  },
  friends: [
    {
      id: "u2",
      name: "Марія Коваль",
      username: "maria.k",
      initials: "МК",
      tone: "lavender",
    },
    {
      id: "u3",
      name: "Олег Бойчук",
      username: "oleh.b",
      initials: "ОБ",
      tone: "peach",
    },
    {
      id: "u4",
      name: "Софія Мельник",
      username: "sofiia.m",
      initials: "СМ",
      tone: "mint",
    },
  ],
  requests: [
    {
      id: "r1",
      name: "Анастасія Гнатюк",
      username: "nastia.h",
      initials: "АГ",
      tone: "blue",
      direction: "incoming",
    },
  ],
  tests: [
    {
      id: "t1",
      title: "Основи баз даних",
      subject: "Інформатика",
      description: "Моделі даних, ключі, зв’язки та SQL-запити.",
      difficulty: "Середній",
      questionCount: 3,
      duration: 5,
      ownerId: "u1",
      ownerName: "Ви",
      createdAt: "2026-10-08",
      accent: "lavender",
      favorite: true,
      questions: [
        {
          text: "Що означає первинний ключ у реляційній таблиці?",
          options: [
            "Унікальний ідентифікатор запису",
            "Назва бази даних",
            "Зовнішнє посилання на сервер",
            "Тип індексу",
          ],
          correct: 0,
        },
        {
          text: "Яка команда SQL використовується для вибірки даних?",
          options: ["INSERT", "SELECT", "UPDATE", "DELETE"],
          correct: 1,
        },
        {
          text: "Для чого потрібен зовнішній ключ?",
          options: [
            "Для шифрування полів",
            "Для зв’язку таблиць",
            "Для видалення БД",
            "Для сортування",
          ],
          correct: 1,
        },
      ],
    },
    {
      id: "t2",
      title: "Алгоритми та структури даних",
      subject: "Програмування",
      description: "Масиви, списки, сортування й оцінка складності.",
      difficulty: "Складний",
      questionCount: 3,
      duration: 5,
      ownerId: "u1",
      ownerName: "Ви",
      createdAt: "2026-10-05",
      accent: "blue",
      favorite: false,
      questions: [
        {
          text: "Яка асимптотична складність бінарного пошуку?",
          options: ["O(n)", "O(log n)", "O(n²)", "O(1)"],
          correct: 1,
        },
        {
          text: "Яка структура даних працює за принципом FIFO?",
          options: ["Стек", "Черга", "Дерево", "Граф"],
          correct: 1,
        },
        {
          text: "Яке сортування в середньому має складність O(n log n)?",
          options: ["Бульбашкове", "Вставками", "Швидке", "Вибором"],
          correct: 2,
        },
      ],
    },
    {
      id: "t3",
      title: "Англійська для IT",
      subject: "Англійська мова",
      description: "Технічна лексика та слова у контексті розробки.",
      difficulty: "Легкий",
      questionCount: 3,
      duration: 5,
      ownerId: "u2",
      ownerName: "Марія Коваль",
      createdAt: "2026-10-07",
      accent: "peach",
      favorite: true,
      questions: [
        {
          text: "Як перекладається слово “deployment”?",
          options: ["Розгортання", "Налагодження", "Збереження", "Тестування"],
          correct: 0,
        },
        {
          text: "Що означає “bug” у розробці?",
          options: ["Функція", "Помилка", "Збірка", "Гілка"],
          correct: 1,
        },
        {
          text: "Яке слово означає “вимога”?",
          options: ["Feature", "Requirement", "Release", "Issue"],
          correct: 1,
        },
      ],
    },
    {
      id: "t4",
      title: "Комп’ютерні мережі",
      subject: "Інформатика",
      description: "Протоколи, IP-адресація та модель OSI.",
      difficulty: "Середній",
      questionCount: 3,
      duration: 5,
      ownerId: "u3",
      ownerName: "Олег Бойчук",
      createdAt: "2026-10-03",
      accent: "mint",
      favorite: false,
      questions: [
        {
          text: "Який протокол використовує браузер для захищеного з’єднання?",
          options: ["FTP", "HTTP", "HTTPS", "SMTP"],
          correct: 2,
        },
        {
          text: "Скільки рівнів має модель OSI?",
          options: ["4", "5", "7", "8"],
          correct: 2,
        },
        {
          text: "Для чого призначена IP-адреса?",
          options: [
            "Для ідентифікації пристрою в мережі",
            "Для шифрування файлів",
            "Для запуску ОС",
            "Для збереження паролів",
          ],
          correct: 0,
        },
      ],
    },
    {
      id: "t5",
      title: "Основи вебдизайну",
      subject: "Дизайн",
      description: "Композиція, типографіка та адаптивні інтерфейси.",
      difficulty: "Легкий",
      questionCount: 3,
      duration: 5,
      ownerId: "u4",
      ownerName: "Софія Мельник",
      createdAt: "2026-10-06",
      accent: "lavender",
      favorite: false,
      questions: [
        {
          text: "Що означає адаптивний дизайн?",
          options: [
            "Підлаштування інтерфейсу під розмір екрана",
            "Один фіксований макет",
            "Тільки мобільну версію",
            "Лише зміну кольорів",
          ],
          correct: 0,
        },
        {
          text: "Який принцип допомагає виділити головну дію на сторінці?",
          options: [
            "Візуальна ієрархія",
            "Випадкове розміщення",
            "Однаковий розмір усього",
            "Відсутність відступів",
          ],
          correct: 0,
        },
        {
          text: "Для чого використовують типографіку?",
          options: [
            "Для читабельності та ієрархії тексту",
            "Лише для анімації",
            "Для зберігання даних",
            "Для створення API",
          ],
          correct: 0,
        },
      ],
    },
  ],
  attempts: [
    { id: "a1", testId: "t1", score: 83, completedAt: "2026-10-10T14:30:00" },
    { id: "a2", testId: "t3", score: 90, completedAt: "2026-10-09T11:15:00" },
    { id: "a3", testId: "t2", score: 67, completedAt: "2026-10-07T17:45:00" },
    { id: "a4", testId: "t1", score: 75, completedAt: "2026-10-02T09:20:00" },
    { id: "a5", testId: "t4", score: 80, completedAt: "2026-09-30T15:10:00" },
  ],
  friendAttempts: [
    {
      id: "fa1",
      userId: "u2",
      testId: "t3",
      score: 93,
      completedAt: "2026-10-11T16:30:00",
    },
    {
      id: "fa2",
      userId: "u2",
      testId: "t1",
      score: 87,
      completedAt: "2026-10-06T12:10:00",
    },
    {
      id: "fa3",
      userId: "u2",
      testId: "t3",
      score: 80,
      completedAt: "2026-10-01T14:00:00",
    },
    {
      id: "fa4",
      userId: "u3",
      testId: "t4",
      score: 78,
      completedAt: "2026-10-10T10:25:00",
    },
    {
      id: "fa5",
      userId: "u3",
      testId: "t2",
      score: 84,
      completedAt: "2026-10-04T15:40:00",
    },
    {
      id: "fa6",
      userId: "u4",
      testId: "t5",
      score: 96,
      completedAt: "2026-10-09T18:20:00",
    },
    {
      id: "fa7",
      userId: "u4",
      testId: "t3",
      score: 91,
      completedAt: "2026-10-02T11:55:00",
    },
  ],
};

const key = () => `forma.lab67.v2.account.${window.__FORMA_ACCOUNT__?.id ?? "guest"}`;
function accountData(data) {
  const account = window.__FORMA_ACCOUNT__;
  if (!account) return data;
  const username = account.username || account.email.split("@")[0];
  const name = account.display_name || username;
  const user = {
    id: String(account.id),
    name,
    username,
    initials: name.slice(0, 2).toUpperCase(),
  };
  return {
    ...data,
    user,
    tests: data.tests.map((test) =>
      test.ownerId === "u1" ? { ...test, ownerId: user.id } : test,
    ),
  };
}
export function readData() {
  try {
    const stored = JSON.parse(localStorage.getItem(key()));
    if (!stored) return accountData(structuredClone(initial));
    // Existing demos created before friend profiles retain their own tests/attempts.
    // Add only the new profile data; do not reset the user's local work.
    return accountData({
      ...stored,
      // Correct the old demo identity while preserving saved tests and attempts.
      user:
        stored.user?.name === "Данило Семкович"
          ? { ...stored.user, name: initial.user.name, username: initial.user.username }
          : (stored.user ?? structuredClone(initial.user)),
      tests: stored.tests.some((test) => test.id === "t5")
        ? stored.tests
        : [
            ...stored.tests,
            structuredClone(initial.tests.find((test) => test.id === "t5")),
          ],
      friendAttempts:
        stored.friendAttempts ?? structuredClone(initial.friendAttempts),
    });
  } catch {
    return accountData(structuredClone(initial));
  }
}
export function saveData(data) {
  localStorage.setItem(key(), JSON.stringify(data));
}
export function resetData() {
  localStorage.removeItem(key());
}
