<script>
  let name = '';
  let message = 'Enter your name and ask the Python API to say hello.';
  let loading = false;
  let error = '';

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
  <title>Svelte + Python</title>
</svelte:head>

<main>
  <section class="card">
    <div class="eyebrow">Native web stack</div>
    <h1>Svelte meets Python</h1>
    <p class="intro">
      This page is rendered by Svelte. The greeting below comes from a FastAPI endpoint.
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

    <div class="stack">
      <span>Svelte</span>
      <span>Vite</span>
      <span>FastAPI</span>
      <span>Python</span>
    </div>
  </section>
</main>

