<script>
  import { onMount } from 'svelte';

  let authState = 'checking';
  let authMessage = 'Checking your application session…';
  let user = null;
  let username = '';
  let password = '';
  let localLoginLoading = false;

  let name = '';
  let message = 'Enter your name and ask the Python API to say hello.';
  let loading = false;
  let error = '';

  onMount(() => {
    bootstrapAuthentication();
  });

  async function bootstrapAuthentication() {
    const localLoginRequested = window.location.pathname === '/login';

    try {
      const response = await fetch('/api/auth/me', {
        credentials: 'same-origin',
        cache: 'no-store'
      });

      if (response.ok) {
        const data = await response.json();
        user = data.user;
        authState = 'authenticated';
        if (localLoginRequested) {
          window.history.replaceState({}, '', '/');
        }
        return;
      }
    } catch {
      showLocalLogin('The application API is unavailable.');
      return;
    }

    if (localLoginRequested) {
      showLocalLogin(reasonMessage());
      return;
    }

    await attemptKerberosLogin();
  }

  async function attemptKerberosLogin() {
    authState = 'kerberos';
    authMessage = 'Signing in with your Windows domain account…';

    try {
      const startResponse = await fetch('/api/auth/kerberos/start', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      const start = await readJson(startResponse);

      if (!startResponse.ok) {
        throw new Error(start.detail || 'Unable to start Kerberos authentication.');
      }

      // The browser must contact Casdoor directly so it can answer the
      // WWW-Authenticate: Negotiate challenge with the logged-in Windows user.
      const kerberosResponse = await fetch(start.kerberos_url, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store'
      });
      const kerberos = await readJson(kerberosResponse);

      if (!kerberosResponse.ok || kerberos.status !== 'ok' || !kerberos.data) {
        throw new Error(kerberos.msg || 'Windows authentication was not accepted.');
      }

      const callback = new URL('/api/auth/callback', window.location.origin);
      callback.searchParams.set('code', kerberos.data);
      callback.searchParams.set('state', start.state);
      window.location.assign(callback.toString());
    } catch (exception) {
      const detail =
        exception instanceof Error ? exception.message : 'Windows authentication failed.';
      showLocalLogin(detail);
    }
  }

  async function submitLocalLogin() {
    localLoginLoading = true;
    authMessage = '';

    try {
      const response = await fetch('/api/auth/local-login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await readJson(response);

      if (!response.ok) {
        throw new Error(data.detail || 'Invalid username or password.');
      }

      password = '';
      user = data.user;
      authState = 'authenticated';
      window.history.replaceState({}, '', '/');
    } catch (exception) {
      authMessage = exception instanceof Error ? exception.message : 'Local login failed.';
    } finally {
      localLoginLoading = false;
    }
  }

  async function retryKerberos() {
    window.history.replaceState({}, '', '/');
    await attemptKerberosLogin();
  }

  async function logout() {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin'
    });
    window.location.assign('/login?reason=signed_out');
  }

  function showLocalLogin(detail = '') {
    authState = 'local';
    authMessage = detail;
    if (window.location.pathname !== '/login') {
      window.history.replaceState({}, '', '/login?reason=kerberos_failed');
    }
  }

  function reasonMessage() {
    const reason = new URLSearchParams(window.location.search).get('reason');
    const messages = {
      invalid_state: 'The authentication request expired. Try Windows sign-in again.',
      token_exchange_failed: 'Casdoor could not complete the sign-in.',
      signed_out: 'You have signed out.',
      kerberos_failed: 'Windows authentication was not available.'
    };
    return messages[reason] || '';
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch {
      return {};
    }
  }

  async function sayHello() {
    loading = true;
    error = '';

    try {
      const params = new URLSearchParams({ name: name.trim() || 'World' });
      const response = await fetch(`/api/hello?${params}`);

      if (!response.ok) {
        throw new Error(`The API returned status ${response.status}`);
      }

      const data = await response.json();
      message = data.message;
    } catch (exception) {
      error = exception instanceof Error ? exception.message : 'Unable to contact the API.';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Svelte + Python Authentication Test</title>
</svelte:head>

<main>
  {#if authState === 'checking' || authState === 'kerberos'}
    <section class="card status-card" aria-live="polite">
      <div class="spinner" aria-hidden="true"></div>
      <div class="eyebrow">Windows authentication</div>
      <h1>Signing you in</h1>
      <p class="intro">{authMessage}</p>
    </section>
  {:else if authState === 'local'}
    <section class="card">
      <div class="eyebrow">Fallback authentication</div>
      <h1>Application login</h1>
      <p class="intro">
        Kerberos sign-in was unavailable. Use a local application account to continue.
      </p>

      <form on:submit|preventDefault={submitLocalLogin}>
        <label for="username">Username</label>
        <input
          id="username"
          bind:value={username}
          autocomplete="username"
          required
        />

        <label for="password">Password</label>
        <input
          id="password"
          type="password"
          bind:value={password}
          autocomplete="current-password"
          required
        />

        <button class="full-width" type="submit" disabled={localLoginLoading}>
          {localLoginLoading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      {#if authMessage}
        <div class="result error" aria-live="polite">{authMessage}</div>
      {/if}

      <button class="secondary full-width" type="button" on:click={retryKerberos}>
        Try Windows sign-in again
      </button>
    </section>
  {:else}
    <section class="card">
      <div class="session-row">
        <div>
          <div class="eyebrow">Authenticated</div>
          <strong>{user?.displayName || user?.name || user?.preferred_username || 'User'}</strong>
          <span class="auth-source">via {user?.auth_source || 'Casdoor'}</span>
        </div>
        <button class="secondary" type="button" on:click={logout}>Sign out</button>
      </div>

      <h1>Svelte meets Python</h1>
      <p class="intro">
        Your application session is active. The greeting below comes from Litestar.
      </p>

      <form on:submit|preventDefault={sayHello}>
        <label for="name">Your name</label>
        <div class="controls">
          <input id="name" bind:value={name} placeholder="World" autocomplete="name" />
          <button type="submit" disabled={loading}>
            {loading ? 'Calling API…' : 'Say hello'}
          </button>
        </div>
      </form>

      <div class:error={error} class="result" aria-live="polite">
        {error || message}
      </div>
    </section>
  {/if}
</main>
