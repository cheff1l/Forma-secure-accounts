import { http, HttpResponse, delay } from "msw";
import { readData, saveData } from "./data";

const ok = async (value) => {
  await delay(180);
  return HttpResponse.json(value);
};
const error = (message, status = 400) =>
  HttpResponse.json({ message }, { status });
const average = (attempts) =>
  attempts.length
    ? Math.round(
        attempts.reduce((sum, a) => sum + a.score, 0) / attempts.length,
      )
    : 0;

export const handlers = [
  http.get("/api/overview", async () => {
    const data = readData();
    return ok({
      user: data.user,
      average: average(data.attempts),
      attempts: data.attempts,
      ownCount: data.tests.filter((t) => t.ownerId === data.user.id).length,
      favoritesCount: data.tests.filter((t) => t.favorite).length,
      friendsCount: data.friends.length,
      tests: data.tests,
    });
  }),
  http.get("/api/tests", async () => ok(readData().tests)),
  http.post("/api/tests", async ({ request }) => {
    const body = await request.json();
    if (!body.title?.trim() || !body.material?.trim())
      return error("Заповніть назву та навчальний матеріал.");
    const data = readData();
    const difficulty =
      body.difficulty === "Адаптивна"
        ? average(data.attempts) >= 80
          ? "Складний"
          : average(data.attempts) >= 60
            ? "Середній"
            : "Легкий"
        : body.difficulty;
    const sentences = body.material
      .split(/[.!?\n]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 12);
    const topics = sentences.length ? sentences : [body.material.trim()];
    const count = Math.min(Number(body.questionCount) || 5, 20);
    const questions = Array.from({ length: count }, (_, i) => ({
      text: `Яке твердження відповідає матеріалу: «${topics[i % topics.length].slice(0, 95)}»?`,
      options: [
        topics[i % topics.length].slice(0, 110),
        "Це твердження не пов’язане з матеріалом",
        "Правильної відповіді немає",
        "Усі наведені твердження помилкові",
      ],
      correct: 0,
    }));
    const test = {
      id: crypto.randomUUID(),
      title: body.title.trim(),
      subject: body.subject?.trim() || "Мій предмет",
      description: body.material.trim().slice(0, 105),
      difficulty,
      questionCount: questions.length,
      duration: Math.max(5, questions.length * 2),
      ownerId: data.user.id,
      ownerName: "Ви",
      createdAt: new Date().toISOString().slice(0, 10),
      accent: "lavender",
      favorite: false,
      questions,
      material: body.material.trim(),
      demoGenerated: true,
    };
    data.tests.unshift(test);
    saveData(data);
    return ok(test);
  }),
  http.patch("/api/tests/:id", async ({ params, request }) => {
    const data = readData();
    const test = data.tests.find((t) => t.id === params.id);
    if (!test) return error("Тест не знайдено.", 404);
    if (test.ownerId !== data.user.id)
      return error("Можна редагувати лише власні тести.", 403);
    const body = await request.json();
    if (!body.title?.trim()) return error("Укажіть назву тесту.");
    Object.assign(test, {
      title: body.title.trim(),
      subject: body.subject?.trim() || "Мій предмет",
      description: body.description?.trim() || test.description,
    });
    saveData(data);
    return ok(test);
  }),
  http.delete("/api/tests/:id", async ({ params }) => {
    const data = readData();
    const test = data.tests.find((t) => t.id === params.id);
    if (!test) return error("Тест не знайдено.", 404);
    if (test.ownerId !== data.user.id)
      return error("Можна видаляти лише власні тести.", 403);
    data.tests = data.tests.filter((t) => t.id !== params.id);
    saveData(data);
    return ok({ success: true });
  }),
  http.post("/api/favorites", async ({ request }) => {
    const { testId } = await request.json();
    const data = readData();
    const test = data.tests.find((t) => t.id === testId);
    if (!test) return error("Тест не знайдено.", 404);
    test.favorite = !test.favorite;
    saveData(data);
    return ok({ favorite: test.favorite });
  }),
  http.post("/api/attempts", async ({ request }) => {
    const { testId, answers } = await request.json();
    const data = readData();
    const test = data.tests.find((t) => t.id === testId);
    if (!test) return error("Тест не знайдено.", 404);
    const right = test.questions.reduce(
      (n, q, i) => n + (answers[i] === q.correct ? 1 : 0),
      0,
    );
    const attempt = {
      id: crypto.randomUUID(),
      testId,
      score: Math.round((right / test.questions.length) * 100),
      correct: right,
      total: test.questions.length,
      completedAt: new Date().toISOString(),
      // Keep a snapshot so the review remains accurate after a test is edited or deleted.
      review: test.questions.map((question, index) => ({
        text: question.text,
        options: [...question.options],
        selected: answers[index] ?? null,
        correct: question.correct,
      })),
    };
    data.attempts.unshift(attempt);
    saveData(data);
    return ok(attempt);
  }),
  http.get("/api/friends", async () => {
    const { friends, requests } = readData();
    return ok({ friends, requests });
  }),
  http.get("/api/friends/:id/profile", async ({ params }) => {
    const data = readData();
    // Profiles are visible only after a friend request has been accepted.
    const friend = data.friends.find((person) => person.id === params.id);
    if (!friend) return error("Профіль друга недоступний.", 404);
    const tests = data.tests.filter((test) => test.ownerId === friend.id);
    const attempts = (data.friendAttempts || [])
      .filter((attempt) => attempt.userId === friend.id)
      .sort((a, b) => new Date(b.completedAt) - new Date(a.completedAt))
      .map((attempt) => ({
        ...attempt,
        testTitle:
          data.tests.find((test) => test.id === attempt.testId)?.title ||
          "Видалений тест",
      }));
    return ok({
      friend,
      tests,
      attempts,
      average: average(attempts),
      best: attempts.length
        ? Math.max(...attempts.map((item) => item.score))
        : 0,
    });
  }),
  http.post("/api/friend-requests", async ({ request }) => {
    const { username } = await request.json();
    const data = readData();
    const value = username?.trim().replace(/^@/, "");
    if (!value) return error("Укажіть ім’я користувача.");
    if (
      value === data.user.username ||
      data.friends.some((f) => f.username === value) ||
      data.requests.some((r) => r.username === value)
    )
      return error("Цей користувач уже є у вашому списку.");
    const person = {
      id: crypto.randomUUID(),
      name: value,
      username: value,
      initials: value.slice(0, 2).toUpperCase(),
      tone: "blue",
      direction: "outgoing",
    };
    data.requests.push(person);
    saveData(data);
    return ok(person);
  }),
  http.patch("/api/friend-requests/:id", async ({ params, request }) => {
    const { action } = await request.json();
    const data = readData();
    const person = data.requests.find((r) => r.id === params.id);
    if (!person || person.direction !== "incoming")
      return error("Запит не знайдено.", 404);
    data.requests = data.requests.filter((r) => r.id !== params.id);
    if (action === "accept")
      data.friends.push({ ...person, direction: undefined });
    saveData(data);
    return ok({ success: true });
  }),
];
