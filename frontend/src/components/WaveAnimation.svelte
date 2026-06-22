<script>
  export let state = 'LISTENING';

  const bars = 5;

  $: isActive = state === 'LISTENING' || state === 'SPEAKING';
  $: isProcessing = state === 'PROCESSING';
</script>

<div class="wave" class:active={isActive} class:processing={isProcessing}>
  {#if isProcessing}
    <div class="spinner">
      <div class="spinner-dot"></div>
      <div class="spinner-dot"></div>
      <div class="spinner-dot"></div>
    </div>
  {:else}
    {#each Array(bars) as _, i}
      <div
        class="bar"
        style="animation-delay: {i * 120}ms; height: {12 + Math.sin(i * 1.2) * 8}px"
      ></div>
    {/each}
  {/if}
</div>

<style>
  .wave {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    height: 40px;
  }

  .bar {
    width: 4px;
    border-radius: 2px;
    background: #6c63ff;
    opacity: 0.4;
    transform-origin: center;
    transition: opacity 300ms ease;
  }

  .wave.active .bar {
    opacity: 1;
    animation: waveBar 1s ease-in-out infinite alternate;
  }

  @keyframes waveBar {
    0% { transform: scaleY(0.4); opacity: 0.5; }
    50% { transform: scaleY(1.6); opacity: 1; }
    100% { transform: scaleY(0.6); opacity: 0.7; }
  }

  /* Processing spinner */
  .spinner {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .spinner-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #6c63ff;
    animation: spinnerPulse 1.2s ease-in-out infinite;
  }
  .spinner-dot:nth-child(2) { animation-delay: 200ms; }
  .spinner-dot:nth-child(3) { animation-delay: 400ms; }

  @keyframes spinnerPulse {
    0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
    40% { transform: scale(1); opacity: 1; }
  }
</style>
