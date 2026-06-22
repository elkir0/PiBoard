<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  const rows = [
    ['a','z','e','r','t','y','u','i','o','p'],
    ['q','s','d','f','g','h','j','k','l','m'],
    ['w','x','c','v','b','n','DEL'],
    ['ESPACE'],
  ];

  function onKey(key) {
    if (key === 'DEL') {
      dispatch('key', { action: 'delete' });
    } else if (key === 'ESPACE') {
      dispatch('key', { action: 'space' });
    } else {
      dispatch('key', { action: 'char', char: key });
    }
  }
</script>

<div class="keyboard">
  {#each rows as row}
    <div class="kb-row">
      {#each row as key}
        <button
          class="kb-key"
          class:wide={key === 'ESPACE'}
          class:del={key === 'DEL'}
          on:click|preventDefault|stopPropagation={() => onKey(key)}
        >
          {#if key === 'DEL'}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22 3H7c-.69 0-1.23.35-1.59.88L0 12l5.41 8.11c.36.53.9.89 1.59.89h15c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-3 12.59L17.59 17 14 13.41 10.41 17 9 15.59 12.59 12 9 8.41 10.41 7 14 10.59 17.59 7 19 8.41 15.41 12 19 15.59z"/>
            </svg>
          {:else if key === 'ESPACE'}
            espace
          {:else}
            {key}
          {/if}
        </button>
      {/each}
    </div>
  {/each}
</div>

<style>
  .keyboard {
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding: 8px 4px;
    background: rgba(20, 20, 30, 0.95);
    border-top: 1px solid rgba(255,255,255,0.08);
  }

  .kb-row {
    display: flex;
    justify-content: center;
    gap: 4px;
  }

  .kb-key {
    min-width: 42px;
    height: 48px;
    border: none;
    border-radius: 8px;
    background: rgba(255,255,255,0.08);
    color: #f0f0f0;
    font-size: 18px;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    -webkit-tap-highlight-color: transparent;
    padding: 0 8px;
  }
  .kb-key:active {
    background: rgba(108, 99, 255, 0.3);
  }

  .kb-key.wide {
    flex: 1;
    max-width: 300px;
    font-size: 14px;
    color: #888;
    letter-spacing: 2px;
  }

  .kb-key.del {
    min-width: 60px;
    color: #ff6b6b;
  }
</style>
