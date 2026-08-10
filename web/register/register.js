const registerForm = document.getElementById('register-form');
const registerUserInput = document.getElementById('register-user');
const registerPasswordInput = document.getElementById('register-password');
const registerPasswordConfirmInput = document.getElementById('register-password-confirm');
const registerSecretInput = document.getElementById('register-secret');
const registerSubmit = document.getElementById('register-submit');
const registerError = document.getElementById('register-error');
const registerSuccess = document.getElementById('register-success');

// See web/app.js for why this isn't a single hardcoded constant.
const REGISTER_ENDPOINT = (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
  ? 'http://localhost:5000/api/register'
  : '/api/register';
const TOKEN_KEY = 'tsvision_token';
const USER_KEY = 'tsvision_user';

function showError(message) {
  registerError.textContent = message;
  registerError.hidden = false;
  registerSuccess.hidden = true;
}

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  registerError.hidden = true;
  registerSuccess.hidden = true;

  const usuario = registerUserInput.value.trim();
  const senha = registerPasswordInput.value;
  const confirmacao = registerPasswordConfirmInput.value;
  const segredo = registerSecretInput.value;

  if (!usuario || !senha || !segredo) {
    showError('Preencha usuário, senha e segredo de registro.');
    return;
  }

  if (senha !== confirmacao) {
    showError('As senhas não conferem.');
    registerPasswordConfirmInput.value = '';
    return;
  }

  registerSubmit.disabled = true;
  registerSubmit.textContent = 'Criando...';

  try {
    const response = await fetch(REGISTER_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, senha, segredo }),
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      showError(data.message || 'Não foi possível criar a conta.');
      return;
    }

    // O backend já devolve um token: entra direto com a conta recém-criada.
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, data.usuario);
    registerForm.reset();
    registerSuccess.textContent = `Conta "${data.usuario}" criada. Entrando...`;
    registerSuccess.hidden = false;
    setTimeout(() => {
      window.location.href = '../';
    }, 900);
  } catch (error) {
    showError(`Não foi possível falar com o servidor: ${error.message}`);
  } finally {
    registerSubmit.disabled = false;
    registerSubmit.textContent = 'Criar conta';
  }
});
