const password = document.querySelector('input[name="password"]');
const confirmation = document.querySelector('input[name="password_confirm"]');
const rules = document.querySelector('#password-rules');
document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  const input = document.getElementById(button.dataset.passwordToggle);
  if (!input) return;
  button.addEventListener('click', () => {
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(visible));
    button.setAttribute('aria-label', `${visible ? 'Приховати' : 'Показати'} ${button.dataset.passwordToggle.endsWith('password_confirm') ? 'підтвердження пароля' : 'пароль'}`);
    button.title = visible ? 'Приховати пароль' : 'Показати пароль';
    button.querySelector('.eye-open').hidden = visible;
    button.querySelector('.eye-closed').hidden = !visible;
    input.focus({ preventScroll: true });
  });
});
if (password && rules) {
  const checks = {
    length: (value) => value.length >= 8,
    upper: (value) => /[A-ZА-ЯІЇЄҐ]/.test(value),
    lower: (value) => /[a-zа-яіїєґ]/.test(value),
    digit: (value) => /\d/.test(value),
    special: (value) => /[^\p{L}\p{N}\s]/u.test(value),
  };
  const update = () => {
    for (const [name, check] of Object.entries(checks)) {
      rules.querySelector(`[data-rule="${name}"]`).classList.toggle('met', check(password.value));
    }
  };
  password.addEventListener('input', update);
  update();
}
if (password && confirmation) {
  const status = document.querySelector('#password-match');
  const update = () => {
    const hasValue = confirmation.value.length > 0;
    const matches = password.value === confirmation.value;
    confirmation.setCustomValidity(hasValue && !matches ? 'Паролі не збігаються.' : '');
    if (status) {
      status.textContent = hasValue ? (matches ? 'Паролі збігаються.' : 'Паролі не збігаються.') : '';
      status.classList.toggle('matched', hasValue && matches);
    }
  };
  password.addEventListener('input', update);
  confirmation.addEventListener('input', update);
}
