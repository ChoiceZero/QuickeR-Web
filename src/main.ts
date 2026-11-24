import '@material/web/button/filled-button.js';
import '@material/web/button/filled-tonal-button.js';
import '@material/web/button/outlined-button.js';
import '@material/web/button/text-button.js';
import '@material/web/chips/chip-set.js';
import '@material/web/chips/filter-chip.js';
import '@material/web/dialog/dialog.js';
import '@material/web/divider/divider.js';
import '@material/web/icon/icon.js';
import '@material/web/iconbutton/icon-button.js';
import '@material/web/list/list.js';
import '@material/web/list/list-item.js';
import '@material/web/select/outlined-select.js';
import '@material/web/select/select-option.js';
import '@material/web/switch/switch.js';
import '@material/web/textfield/outlined-text-field.js';

import type { MdDialog } from '@material/web/dialog/dialog.js';
import type { MdFilterChip } from '@material/web/chips/filter-chip.js';
import type { MdOutlinedSelect } from '@material/web/select/outlined-select.js';
import type { MdOutlinedTextField } from '@material/web/textfield/outlined-text-field.js';
import type { MdSwitch } from '@material/web/switch/switch.js';

import './styles.css';
import { icons, type IconName } from './ui/icons';
import { applyTheme, loadSavedTheme, saveTheme, SEED_COLORS, systemMode, type Mode } from './theme';
import {
  buildPayload, emptyValues, hasContent, sanitizeFilename, validate,
  type FieldName, type FormValues, type QrType, type WifiSecurity,
} from './qr/payload';
import { canBeScanned, qrVersionInfo, renderQr, type ErrorCorrection } from './qr/render';
import { contrastLevel } from './qr/color';

declare const __APP_VERSION__: string;

const $ = <T extends Element = HTMLElement>(selector: string, root: ParentNode = document) =>
  root.querySelector<T>(selector)!;
const $$ = <T extends Element = HTMLElement>(selector: string, root: ParentNode = document) =>
  [...root.querySelectorAll<T>(selector)];

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function iconSvg(name: IconName): string {
  return icons[name] ?? '';
}

function hydrateIcons(root: ParentNode = document): void {
  for (const el of $$<HTMLElement>('md-icon[data-icon]', root)) {
    el.innerHTML = iconSvg(el.dataset.icon as IconName);
  }
}

function setIcon(el: Element, name: IconName): void {
  (el as HTMLElement).dataset.icon = name;
  el.innerHTML = iconSvg(name);
}

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

const savedTheme = loadSavedTheme();
const theme = {
  // Like the QuickeR app, a random accent is picked unless one was chosen.
  seed: savedTheme.seed ?? SEED_COLORS[Math.floor(Math.random() * SEED_COLORS.length)].hex,
  mode: savedTheme.mode ?? systemMode(),
};

function refreshTheme(): void {
  applyTheme(theme.seed, theme.mode);
  const modeButton = $('#mode-button');
  const next: Mode = theme.mode === 'dark' ? 'light' : 'dark';
  modeButton.setAttribute('aria-label', `Switch to ${next} theme`);
  setIcon($('md-icon', modeButton), theme.mode === 'dark' ? 'lightMode' : 'darkMode');
  for (const swatch of $$<HTMLButtonElement>('.palette-menu button')) {
    swatch.setAttribute('aria-checked', String(swatch.dataset.seed === theme.seed));
  }
}

function setupThemeControls(): void {
  $('#mode-button').addEventListener('click', () => {
    theme.mode = theme.mode === 'dark' ? 'light' : 'dark';
    saveTheme({ mode: theme.mode });
    refreshTheme();
  });

  const menu = $('#palette-menu');
  const button = $('#palette-button');
  for (const { name, hex } of SEED_COLORS) {
    const swatch = document.createElement('button');
    swatch.type = 'button';
    swatch.className = 'palette-swatch';
    swatch.dataset.seed = hex;
    swatch.style.setProperty('--swatch', hex);
    swatch.setAttribute('role', 'menuitemradio');
    swatch.setAttribute('aria-label', name);
    swatch.title = name;
    swatch.innerHTML = `<md-icon>${iconSvg('check')}</md-icon>`;
    swatch.addEventListener('click', () => {
      theme.seed = hex;
      saveTheme({ seed: hex });
      refreshTheme();
      closeMenu();
    });
    menu.append(swatch);
  }

  const onOutside = (event: Event) => {
    if (!menu.contains(event.target as Node) && !button.contains(event.target as Node)) closeMenu();
  };
  const onKey = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      closeMenu();
      (button as HTMLElement).focus();
    }
  };
  function openMenu() {
    const rect = button.getBoundingClientRect();
    menu.hidden = false;
    const width = menu.offsetWidth;
    menu.style.top = `${rect.bottom + 8}px`;
    menu.style.left = `${Math.max(16, Math.min(rect.right - width, innerWidth - width - 16))}px`;
    document.addEventListener('pointerdown', onOutside);
    document.addEventListener('keydown', onKey);
    $<HTMLButtonElement>('button[aria-checked="true"]', menu)?.focus();
  }
  function closeMenu() {
    menu.hidden = true;
    document.removeEventListener('pointerdown', onOutside);
    document.removeEventListener('keydown', onKey);
  }
  button.addEventListener('click', () => (menu.hidden ? openMenu() : closeMenu()));
  addEventListener('resize', closeMenu);
}

// ---------------------------------------------------------------------------
// Snackbar and dialogs
// ---------------------------------------------------------------------------

let snackbarTimer = 0;
function snackbar(message: string): void {
  const el = $('#snackbar');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(snackbarTimer);
  snackbarTimer = window.setTimeout(() => el.classList.remove('visible'), 4000);
}

interface DialogAction {
  label: string;
  value: string;
  primary?: boolean;
}

let dialogCount = 0;
/** Shows a Material dialog and resolves with the chosen action's value. */
function ask(options: { icon?: IconName; headline: string; body: string; actions: DialogAction[] }): Promise<string> {
  const dialog = document.createElement('md-dialog') as MdDialog;
  const formId = `dialog-form-${++dialogCount}`;
  dialog.innerHTML = `
    ${options.icon ? `<md-icon slot="icon">${iconSvg(options.icon)}</md-icon>` : ''}
    <div slot="headline"></div>
    <form slot="content" id="${formId}" method="dialog"><p class="dialog-body"></p></form>
    <div slot="actions"></div>`;
  $('[slot="headline"]', dialog).textContent = options.headline;
  $('.dialog-body', dialog).textContent = options.body;
  const actions = $('[slot="actions"]', dialog);
  for (const action of options.actions) {
    const btn = document.createElement(action.primary ? 'md-filled-tonal-button' : 'md-text-button');
    btn.setAttribute('form', formId);
    btn.setAttribute('value', action.value);
    btn.textContent = action.label;
    actions.append(btn);
  }
  document.body.append(dialog);
  return new Promise((resolve) => {
    dialog.addEventListener('closed', () => {
      resolve(dialog.returnValue);
      dialog.remove();
    });
    dialog.show();
  });
}

// ---------------------------------------------------------------------------
// Creator state
// ---------------------------------------------------------------------------

const QR_COLORS = [
  '#000000', '#ffffff', '#424242', '#d32f2f', '#c2185b', '#7b1fa2', '#512da8', '#303f9f',
  '#1976d2', '#0277bd', '#00838f', '#00796b', '#388e3c', '#558b2f', '#f9a825', '#ef6c00',
  '#5d4037', '#455a64',
];

const TYPE_LABELS: Record<QrType, string> = {
  text: 'Text / URL',
  wifi: 'Wi‑Fi',
  email: 'Email',
  phone: 'Phone',
  location: 'Location',
  sms: 'SMS',
  event: 'Event',
  contact: 'Contact',
};

const TYPE_ICONS: Record<QrType, IconName> = {
  text: 'textFields',
  wifi: 'wifi',
  email: 'mail',
  phone: 'call',
  location: 'locationOn',
  sms: 'sms',
  event: 'event',
  contact: 'contactPage',
};

const state = {
  type: 'text' as QrType,
  values: emptyValues(),
  errorCorrection: 'M' as ErrorCorrection,
  foreground: '#000000',
  background: '#ffffff',
  logo: null as HTMLImageElement | null,
  logoUrl: '',
  canvas: null as HTMLCanvasElement | null,
  payload: '',
};

type FieldElement = MdOutlinedTextField | MdOutlinedSelect | MdSwitch;

const fieldElements = () => $$<HTMLElement>('[data-field]') as unknown as FieldElement[];
const fieldName = (el: Element) => (el as HTMLElement).dataset.field as FieldName;

function readField(el: FieldElement): string | boolean {
  return el.tagName === 'MD-SWITCH' ? (el as MdSwitch).selected : (el as MdOutlinedTextField).value;
}

function writeFields(): void {
  for (const el of fieldElements()) {
    const value = state.values[fieldName(el)];
    if (el.tagName === 'MD-SWITCH') (el as MdSwitch).selected = Boolean(value);
    else (el as MdOutlinedTextField).value = String(value);
  }
}

function clearFieldError(el: Element): void {
  const field = el as MdOutlinedTextField;
  if ('error' in field && field.error) {
    field.error = false;
    field.errorText = '';
  }
}

function updateConditionalFields(): void {
  const v = state.values;
  for (const el of $$<HTMLElement>('[data-show-when]')) {
    const rule = el.dataset.showWhen;
    el.hidden = rule === 'wifi-password' ? v.wifiSecurity === 'nopass' : rule === 'email-advanced' ? !v.emailAdvanced : false;
  }
}

function selectType(type: QrType): void {
  state.type = type;
  for (const chip of $$<MdFilterChip>('#type-chips md-filter-chip')) {
    chip.selected = chip.dataset.qrType === type;
  }
  for (const group of $$<HTMLElement>('.fields[data-type]')) {
    group.hidden = group.dataset.type !== type;
  }
  scheduleRender();
}

/** `datetime-local` value for a Date, in local time. */
function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultEventTimes(): Pick<FormValues, 'eventStart' | 'eventEnd'> {
  const start = new Date();
  start.setHours(start.getHours() + 1, 0, 0, 0);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  return { eventStart: toLocalInput(start), eventEnd: toLocalInput(end) };
}

function setupCreator(): void {
  state.values = { ...emptyValues(), ...defaultEventTimes() };
  writeFields();

  for (const chip of $$<MdFilterChip>('#type-chips md-filter-chip')) {
    // Chips toggle themselves on click; re-select so exactly one stays on.
    chip.addEventListener('click', () => selectType(chip.dataset.qrType as QrType));
  }

  for (const el of fieldElements()) {
    const handler = () => {
      const name = fieldName(el);
      if (el.classList.contains('prefix-field')) {
        // Country codes: up to 4 digits.
        const field = el as MdOutlinedTextField;
        const cleaned = field.value.replace(/\D/g, '').slice(0, 4);
        if (cleaned !== field.value) field.value = cleaned;
      }
      const value = readField(el);
      (state.values as unknown as Record<string, string | boolean>)[name] =
        name === 'wifiSecurity' ? (value as WifiSecurity) : value;
      clearFieldError(el);
      updateConditionalFields();
      scheduleRender();
    };
    el.addEventListener('input', handler);
    el.addEventListener('change', handler);
  }

  $('#error-correction').addEventListener('change', (event) => {
    state.errorCorrection = (event.target as MdOutlinedSelect).value as ErrorCorrection;
    scheduleRender();
  });

  $('#name-field').addEventListener('input', () => clearFieldError($('#name-field')));

  $('#locate-button').addEventListener('click', locate);
  setupColorPicker('foreground');
  setupColorPicker('background');
  setupLogo();

  $('#download-button').addEventListener('click', download);
  $('#reset-button').addEventListener('click', reset);

  updateConditionalFields();
  selectType('text');
}

function locate(): void {
  if (!('geolocation' in navigator)) {
    snackbar('Your browser can’t share your location');
    return;
  }
  const button = $('#locate-button') as HTMLElement & { disabled: boolean };
  button.disabled = true;
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      button.disabled = false;
      state.values.latitude = coords.latitude.toFixed(5);
      state.values.longitude = coords.longitude.toFixed(5);
      writeFields();
      for (const el of $$('[data-field="latitude"], [data-field="longitude"]')) clearFieldError(el);
      scheduleRender();
    },
    () => {
      button.disabled = false;
      snackbar('Couldn’t get your location');
    },
    { enableHighAccuracy: true, timeout: 10000 },
  );
}

// ---------------------------------------------------------------------------
// Colors and logo
// ---------------------------------------------------------------------------

function setupColorPicker(which: 'foreground' | 'background'): void {
  const container = $(`#${which}-swatches`);
  const label = $(`#${which}-value`);

  const select = (hex: string) => {
    state[which] = hex.toLowerCase();
    label.textContent = hex.toUpperCase();
    for (const swatch of $$<HTMLElement>('.swatch', container)) {
      const checked = swatch.dataset.color === state[which];
      swatch.setAttribute('aria-checked', String(checked));
      swatch.tabIndex = checked ? 0 : -1;
    }
    const custom = $<HTMLElement>('.swatch-custom', container);
    const isCustom = !QR_COLORS.includes(state[which]);
    custom.setAttribute('aria-checked', String(isCustom));
    custom.style.setProperty('--swatch', isCustom ? state[which] : 'transparent');
    custom.classList.toggle('filled', isCustom);
    scheduleRender();
  };

  for (const hex of QR_COLORS) {
    const swatch = document.createElement('button');
    swatch.type = 'button';
    swatch.className = 'swatch';
    swatch.dataset.color = hex;
    swatch.style.setProperty('--swatch', hex);
    swatch.setAttribute('role', 'radio');
    swatch.setAttribute('aria-label', hex.toUpperCase());
    swatch.title = hex.toUpperCase();
    swatch.innerHTML = `<md-icon>${iconSvg('check')}</md-icon>`;
    swatch.addEventListener('click', () => select(hex));
    container.append(swatch);
  }

  const custom = document.createElement('label');
  custom.className = 'swatch swatch-custom';
  custom.setAttribute('role', 'radio');
  custom.title = 'Custom color';
  custom.innerHTML = `<md-icon>${iconSvg('colorize')}</md-icon><input type="color" aria-label="Custom ${which} color" />`;
  const input = $<HTMLInputElement>('input', custom);
  input.addEventListener('input', () => select(input.value));
  container.append(custom);

  // Arrow keys move between swatches, like a radio group.
  container.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    const items = $$<HTMLElement>('button.swatch', container);
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index < 0) return;
    event.preventDefault();
    const step = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1;
    const next = items[(index + step + items.length) % items.length];
    next.focus();
    next.click();
  });

  select(state[which]);
}

function setupLogo(): void {
  const input = $<HTMLInputElement>('#logo-input');
  $('#logo-button').addEventListener('click', () => input.click());
  $('#logo-remove').addEventListener('click', () => setLogo(null));
  input.addEventListener('change', () => {
    const file = input.files?.[0];
    input.value = '';
    if (file) setLogo(file);
  });
}

function setLogo(file: File | null): void {
  if (state.logoUrl) URL.revokeObjectURL(state.logoUrl);
  state.logo = null;
  state.logoUrl = '';

  const thumb = $('#logo-thumb');
  const apply = () => {
    const hasLogo = state.logo !== null;
    $('#logo-name').textContent = hasLogo && file ? file.name : 'No logo';
    $('#logo-remove').hidden = !hasLogo;
    $('#logo-warning').hidden = !hasLogo;
    thumb.classList.toggle('has-logo', hasLogo);
    thumb.innerHTML = hasLogo ? '' : `<md-icon>${iconSvg('addPhotoAlternate')}</md-icon>`;
    if (hasLogo) thumb.append(state.logo!.cloneNode());
    const select = $<MdOutlinedSelect>('#error-correction');
    select.disabled = hasLogo;
    select.supportingText = hasLogo
      ? 'Locked to H while a logo is added.'
      : 'Higher levels survive damage better but make the code denser.';
    if (hasLogo) select.value = 'H';
    else select.value = state.errorCorrection;
    scheduleRender();
  };

  if (!file) {
    apply();
    return;
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.alt = '';
  img.onload = () => {
    state.logo = img;
    state.logoUrl = url;
    apply();
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    snackbar('That image couldn’t be opened');
    apply();
  };
  img.src = url;
}

// ---------------------------------------------------------------------------
// Preview
// ---------------------------------------------------------------------------

let renderTimer = 0;
function scheduleRender(): void {
  clearTimeout(renderTimer);
  renderTimer = window.setTimeout(render, 80);
}

function render(): void {
  const frame = $('#qr-frame');
  const placeholder = $('#qr-placeholder');
  const status = $('#status-chip');
  const payload = buildPayload(state.type, state.values);
  state.payload = payload;
  frame.style.setProperty('--qr-background', state.background);

  $$('canvas', frame).forEach((c) => c.remove());
  state.canvas = null;

  if (!hasContent(state.type, state.values)) {
    placeholder.hidden = false;
    placeholder.querySelector('span')!.textContent = 'Your QR code will appear here';
    frame.classList.remove('has-qr');
    status.hidden = true;
    renderSummary();
    return;
  }

  try {
    state.canvas = renderQr({
      text: payload,
      errorCorrection: state.errorCorrection,
      foreground: state.foreground,
      background: state.background,
      logo: state.logo,
    });
  } catch {
    placeholder.hidden = false;
    placeholder.querySelector('span')!.textContent = 'There’s too much content for one QR code';
    frame.classList.remove('has-qr');
    setStatus('error', 'Too long');
    renderSummary();
    return;
  }

  state.canvas.setAttribute('role', 'img');
  state.canvas.setAttribute('aria-label', `QR code: ${TYPE_LABELS[state.type]}`);
  placeholder.hidden = true;
  frame.classList.add('has-qr');
  frame.append(state.canvas);

  const contrast = contrastLevel(state.foreground, state.background);
  if (contrast === 'low') setStatus('error', 'Low contrast');
  else if (!canBeScanned(state.canvas, payload)) setStatus('warning', 'May not scan');
  else if (contrast === 'moderate') setStatus('warning', 'Moderate contrast');
  else setStatus('ok', 'Scannable');

  renderSummary();
}

function setStatus(kind: 'ok' | 'warning' | 'error', label: string): void {
  const status = $('#status-chip');
  status.hidden = false;
  status.className = `status-chip ${kind}`;
  status.innerHTML = `<md-icon>${iconSvg(kind === 'ok' ? 'checkCircle' : kind === 'warning' ? 'warning' : 'error')}</md-icon>`;
  status.append(label);
}

function summaryRows(): Array<[string, string]> {
  const v = state.values;
  const phone = (prefix: string, number: string) => (number.trim() ? `+${prefix.trim()} ${number.trim()}` : '');
  const when = (value: string) => (value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '');
  const rows: Array<[string, string]> = [];
  switch (state.type) {
    case 'text':
      rows.push(['Content', v.text]);
      break;
    case 'wifi':
      rows.push(['Network', v.wifiName]);
      rows.push(['Security', v.wifiSecurity === 'nopass' ? 'No password' : v.wifiSecurity]);
      if (v.wifiSecurity !== 'nopass') rows.push(['Password', v.wifiPassword ? '•'.repeat(Math.min(v.wifiPassword.length, 12)) : '']);
      break;
    case 'email':
      rows.push(['Address', v.emailAddress]);
      if (v.emailAdvanced) {
        rows.push(['Subject', v.emailSubject]);
        rows.push(['Message', v.emailBody]);
      }
      break;
    case 'phone':
      rows.push(['Number', phone(v.phonePrefix, v.phoneNumber)]);
      break;
    case 'sms':
      rows.push(['Receiver', phone(v.smsPrefix, v.smsNumber)]);
      rows.push(['Message', v.smsMessage]);
      break;
    case 'location':
      rows.push(['Latitude', v.latitude]);
      rows.push(['Longitude', v.longitude]);
      break;
    case 'event':
      rows.push(['Event', v.eventTitle]);
      rows.push(['Location', v.eventLocation]);
      rows.push(['Starts', when(v.eventStart)]);
      rows.push(['Ends', when(v.eventEnd)]);
      break;
    case 'contact':
      rows.push(['Name', [v.contactFirstName, v.contactLastName].map((s) => s.trim()).filter(Boolean).join(' ')]);
      if (v.contactOrg || v.contactJobTitle) rows.push(['Work', [v.contactJobTitle, v.contactOrg].map((s) => s.trim()).filter(Boolean).join(', ')]);
      if (v.contactPhoneNumber) rows.push(['Phone', phone(v.contactPhonePrefix, v.contactPhoneNumber)]);
      if (v.contactEmail) rows.push(['Email', v.contactEmail]);
      if (v.contactWebsite) rows.push(['Website', v.contactWebsite]);
      break;
  }
  const level = state.logo ? 'H' : state.errorCorrection;
  const info = qrVersionInfo(state.payload, level);
  rows.push(['Correction', `${level}${state.logo ? ' (logo)' : ''}`]);
  if (info && state.canvas) rows.push(['Size', `${state.canvas.width} × ${state.canvas.width} px · version ${info.version}`]);
  return rows;
}

function renderSummary(): void {
  const summary = $('#summary');
  summary.replaceChildren();
  const typeRow = document.createElement('div');
  typeRow.className = 'summary-type';
  typeRow.innerHTML = `<md-icon>${iconSvg(TYPE_ICONS[state.type])}</md-icon>`;
  typeRow.append(TYPE_LABELS[state.type]);
  summary.append(typeRow);
  for (const [label, value] of summaryRows()) {
    const row = document.createElement('div');
    row.className = 'summary-row';
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value || '—';
    dd.classList.toggle('empty', !value);
    row.append(dt, dd);
    summary.append(row);
  }
}

// ---------------------------------------------------------------------------
// Download and reset
// ---------------------------------------------------------------------------

function showFieldErrors(): boolean {
  const errors = validate(state.type, state.values);
  for (const { field, message } of errors) {
    const el = $<MdOutlinedTextField>(`.fields[data-type="${state.type}"] [data-field="${field}"]`);
    if (el && 'errorText' in el) {
      el.error = true;
      el.errorText = message;
    }
  }
  if (errors.length) {
    const first = $<HTMLElement>(`.fields[data-type="${state.type}"] [data-field="${errors[0].field}"]`);
    first?.focus();
    first?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    snackbar(errors.length === 1 ? 'Fill in the highlighted field' : 'Fill in the highlighted fields');
  }
  return errors.length === 0;
}

async function download(): Promise<void> {
  render();
  if (!showFieldErrors()) return;
  if (!state.canvas) {
    snackbar('There’s too much content for one QR code');
    return;
  }

  const nameField = $<MdOutlinedTextField>('#name-field');
  const rawName = nameField.value.trim();
  if (rawName && sanitizeFilename(rawName) !== rawName) {
    nameField.error = true;
    nameField.errorText = 'Can’t contain \\ / : * ? " < > | \'';
    nameField.focus();
    return;
  }

  const contrast = contrastLevel(state.foreground, state.background);
  if (contrast !== 'ok') {
    const choice = await ask({
      icon: 'warning',
      headline: contrast === 'low' ? 'Low contrast' : 'Moderate contrast',
      body: `The selected colors have ${contrast} contrast. This may result in a QR code that is difficult to scan. Do you want to continue?`,
      actions: [
        { label: 'Cancel', value: 'cancel' },
        { label: 'Download anyway', value: 'continue', primary: true },
      ],
    });
    if (choice !== 'continue') return;
  }

  const canvas = state.canvas;
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) {
    snackbar('The image couldn’t be created');
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${rawName || 'quicker-qr'}.png`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  snackbar('QR code downloaded');
}

async function reset(): Promise<void> {
  const choice = await ask({
    icon: 'restartAlt',
    headline: 'Start over?',
    body: 'Everything you entered, the colors and the logo will be cleared.',
    actions: [
      { label: 'Cancel', value: 'cancel' },
      { label: 'Start over', value: 'reset', primary: true },
    ],
  });
  if (choice !== 'reset') return;

  state.values = { ...emptyValues(), ...defaultEventTimes() };
  writeFields();
  fieldElements().forEach(clearFieldError);
  const nameField = $<MdOutlinedTextField>('#name-field');
  nameField.value = '';
  clearFieldError(nameField);
  state.errorCorrection = 'M';
  $<MdOutlinedSelect>('#error-correction').value = 'M';
  for (const which of ['foreground', 'background'] as const) {
    $<HTMLButtonElement>(`#${which}-swatches .swatch[data-color="${which === 'foreground' ? '#000000' : '#ffffff'}"]`).click();
  }
  setLogo(null);
  updateConditionalFields();
  selectType('text');
}

// ---------------------------------------------------------------------------
// About
// ---------------------------------------------------------------------------

function setupAbout(): void {
  const dialog = $<MdDialog>('#about-dialog');
  $('#about-version').textContent = `v${__APP_VERSION__}`;
  const open = () => dialog.show();
  $('#about-button').addEventListener('click', open);
  $('#about-icon-button').addEventListener('click', open);
  $('#share-item').addEventListener('click', async () => {
    const link = 'https://choicezero.github.io/QuickeR-Web/';
    try {
      await navigator.clipboard.writeText(link);
      snackbar('Link copied to clipboard');
    } catch {
      snackbar(link);
    }
  });
}

function setupScrollElevation(): void {
  const bar = $('#top-app-bar');
  const update = () => bar.classList.toggle('scrolled', scrollY > 0);
  addEventListener('scroll', update, { passive: true });
  update();
}

// ---------------------------------------------------------------------------

hydrateIcons();
setupThemeControls();
refreshTheme();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (!loadSavedTheme().mode) {
    theme.mode = systemMode();
    refreshTheme();
  }
});
setupCreator();
setupAbout();
setupScrollElevation();
