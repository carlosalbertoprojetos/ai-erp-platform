import { authService } from '../services/auth-service.js';
import { renderLoginCard, toast } from '../components/ui.js';

export async function renderLoginPage({ shell }) {
  shell.setHeader('Administrator Sign In', 'Authenticate to access the control plane.');
  shell.content.innerHTML = renderLoginCard();
  const form = shell.content.querySelector('#login-form');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = 'Signing in...';
    const formData = new FormData(form);
    try {
      const session = await authService.login(String(formData.get('username')), String(formData.get('password')));
      window.localStorage.setItem('coreflow_admin_username', session.username);
      toast(shell.toastRegion, 'Signed in successfully.');
      window.dispatchEvent(new CustomEvent('coreflow:login-success'));
    } catch (error) {
      shell.content.innerHTML = renderLoginCard(error.message);
      const rerender = await renderLoginPage({ shell });
      return rerender;
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = 'Sign in';
    }
  });
  return () => {};
}
