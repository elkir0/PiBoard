<script>
  import { onMount } from 'svelte';
  import { weatherData, sendWS, wsConnected, currentPage } from '../stores/assistant.js';

  const iconMap = {
    '01d': '☀️', '01n': '🌙', '02d': '⛅', '02n': '☁️',
    '03d': '☁️', '03n': '☁️', '04d': '☁️', '04n': '☁️',
    '09d': '🌧️', '10d': '🌧️', '10n': '🌧️',
    '11d': '⛈️', '13d': '❄️', '50d': '🌫️',
  };

  const dayNames = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];

  function getFrenchDay(dayStr) {
    if (!dayStr) return '';
    // If it's already a short French name, return as-is
    const frenchShort = ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim'];
    if (frenchShort.includes(dayStr.toLowerCase().slice(0, 3))) return dayStr;
    // Try parsing as date
    try {
      const d = new Date(dayStr);
      if (!isNaN(d.getTime())) return dayNames[d.getDay()];
    } catch(e) {}
    return dayStr;
  }

  function cardAccentColor(icon) {
    if (!icon) return 'rgba(255,255,255,0.08)';
    if (icon.startsWith('09') || icon.startsWith('10')) return '#4a9eff';
    if (icon.startsWith('11')) return '#7b68ee';
    if (icon.startsWith('13')) return '#87ceeb';
    if (icon.startsWith('01')) return '#ff9f43';
    if (icon.startsWith('02')) return '#ffb347';
    return '#666';
  }

  function uvColor(uv) {
    if (uv <= 2) return '#4caf50';
    if (uv <= 5) return '#ffeb3b';
    if (uv <= 7) return '#ff9800';
    return '#f44336';
  }

  $: data = $weatherData || {
    loaded: false, city: 'Guadeloupe', temp: '--',
    humidity: '--', wind: '--', condition: 'Chargement...',
    icon: '01d', forecast: []
  };

  $: emoji = iconMap[data.icon] || '☀️';

  // Request weather when navigating to this page (page 1)
  $: if ($currentPage === 1 && !$weatherData && $wsConnected) {
    sendWS({ type: 'weather_refresh' });
  }

  // Also request on WS reconnect if we still don't have data
  $: if ($wsConnected && !$weatherData) {
    sendWS({ type: 'weather_refresh' });
  }
</script>

<div class="weather-page">
  <!-- Main current weather -->
  <div class="current">
    <span class="weather-emoji">{emoji}</span>
    <div class="temp-block">
      <span class="temp">{data.temp}<span class="deg">°</span></span>
      <span class="condition">{data.condition}</span>
      {#if data.feels_like !== undefined && data.feels_like !== null}
        <span class="feels-like">Ressenti {data.feels_like}°</span>
      {/if}
      <span class="city">{data.city}</span>
    </div>
    <div class="details">
      <div class="detail-item">
        <span class="detail-val">{data.humidity}%</span>
        <span class="detail-label">Humidite</span>
      </div>
      <div class="detail-item">
        <span class="detail-val">{data.wind}</span>
        <span class="detail-label">km/h</span>
      </div>
      {#if data.uv !== undefined && data.uv !== null}
        <div class="detail-item">
          <span class="uv-badge" style="background: {uvColor(data.uv)}">
            {data.uv}
          </span>
          <span class="detail-label">UV</span>
        </div>
      {/if}
    </div>
  </div>

  <!-- Sunrise / Sunset -->
  {#if data.sunrise && data.sunset}
    <div class="sun-row">
      <span class="sun-item">↑ {data.sunrise}</span>
      <span class="sun-divider"></span>
      <span class="sun-item">↓ {data.sunset}</span>
    </div>
  {/if}

  <div class="section-divider"></div>

  <!-- Hourly forecast -->
  {#if data.hourly && data.hourly.length > 0}
    <div class="hourly-scroll">
      {#each data.hourly.slice(0, 8) as hour}
        <div class="hourly-item">
          <span class="hourly-time">{hour.time || hour.hour}</span>
          <span class="hourly-emoji">{iconMap[hour.icon] || '☀️'}</span>
          <span class="hourly-temp">{hour.temp}°</span>
        </div>
      {/each}
    </div>
    <div class="section-divider"></div>
  {/if}

  <!-- 3-day forecast -->
  {#if data.forecast && data.forecast.length > 0}
    <div class="forecast">
      {#each data.forecast as day}
        <div class="forecast-card">
          <div class="fc-accent" style="background: {cardAccentColor(day.icon)}"></div>
          <span class="fc-day">{getFrenchDay(day.day)}</span>
          <span class="fc-emoji">{iconMap[day.icon] || '☀️'}</span>
          <span class="fc-temps">{day.high}° <small>{day.low}°</small></span>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .weather-page {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 32px 24px;
    gap: 20px;
  }

  .current {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  .weather-emoji {
    font-size: 72px;
    line-height: 1;
  }

  .temp-block {
    display: flex;
    flex-direction: column;
  }

  .temp {
    font-size: 80px;
    font-weight: 700;
    color: #f0f0f0;
    line-height: 1;
    letter-spacing: -4px;
  }

  .deg {
    font-size: 32px;
    font-weight: 400;
    color: #666;
    letter-spacing: 0;
  }

  .condition {
    font-size: 16px;
    color: #999;
    margin-top: 4px;
  }

  .condition::first-letter {
    text-transform: uppercase;
  }

  .feels-like {
    font-size: 13px;
    color: #666;
    margin-top: 2px;
  }

  .city {
    font-size: 11px;
    color: #555;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 6px;
  }

  .details {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-left: 20px;
    padding-left: 20px;
    border-left: 1px solid rgba(255,255,255,0.06);
  }

  .detail-item {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .detail-val {
    font-size: 18px;
    font-weight: 600;
    color: #f0f0f0;
  }

  .detail-label {
    font-size: 10px;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .uv-badge {
    font-size: 14px;
    font-weight: 700;
    color: #0a0a0f;
    padding: 2px 10px;
    border-radius: 8px;
    line-height: 1.4;
  }

  /* Sunrise / Sunset */
  .sun-row {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .sun-item {
    font-size: 14px;
    color: #888;
    font-weight: 500;
    letter-spacing: 0.5px;
  }

  .sun-divider {
    width: 1px;
    height: 14px;
    background: rgba(255,255,255,0.1);
  }

  /* Section divider */
  .section-divider {
    width: 120px;
    height: 1px;
    background: rgba(255,255,255,0.05);
  }

  /* Hourly forecast */
  .hourly-scroll {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    max-width: 100%;
    padding: 4px 8px;
    scrollbar-width: none;
  }

  .hourly-scroll::-webkit-scrollbar {
    display: none;
  }

  .hourly-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 8px 14px;
    background: rgba(255,255,255,0.03);
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.04);
    min-width: 60px;
    flex-shrink: 0;
  }

  .hourly-time {
    font-size: 11px;
    color: #888;
    font-weight: 500;
  }

  .hourly-emoji {
    font-size: 20px;
    line-height: 1;
  }

  .hourly-temp {
    font-size: 14px;
    font-weight: 600;
    color: #f0f0f0;
  }

  /* Forecast cards */
  .forecast {
    display: flex;
    gap: 12px;
  }

  .forecast-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 14px 22px;
    background: rgba(255,255,255,0.03);
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.05);
    min-width: 90px;
    position: relative;
    overflow: hidden;
    transition: opacity 0.2s ease-out, transform 0.2s ease-out;
  }

  .forecast-card:active {
    transform: scale(0.96);
    opacity: 0.85;
  }

  .fc-accent {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    opacity: 0.7;
  }

  .fc-day {
    font-size: 12px;
    color: #888;
    font-weight: 500;
    text-transform: capitalize;
  }

  .fc-emoji {
    font-size: 26px;
    line-height: 1;
  }

  .fc-temps {
    font-size: 15px;
    font-weight: 600;
    color: #f0f0f0;
  }

  .fc-temps small {
    font-weight: 400;
    color: #555;
    font-size: 13px;
  }
</style>
