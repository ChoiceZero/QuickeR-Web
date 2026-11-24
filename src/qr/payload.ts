// Builds the text encoded in a QR code for each QR type.
// The types and fields mirror the creator of the QuickeR app
// (https://github.com/ChoiceZero/QuickeR).

export type QrType =
  | 'text'
  | 'wifi'
  | 'email'
  | 'phone'
  | 'location'
  | 'sms'
  | 'event'
  | 'contact';

export type WifiSecurity = 'WPA2' | 'WPA' | 'WEP' | 'nopass';

export interface FormValues {
  text: string;
  wifiName: string;
  wifiSecurity: WifiSecurity;
  wifiPassword: string;
  emailAddress: string;
  emailAdvanced: boolean;
  emailSubject: string;
  emailBody: string;
  phonePrefix: string;
  phoneNumber: string;
  smsPrefix: string;
  smsNumber: string;
  smsMessage: string;
  latitude: string;
  longitude: string;
  eventTitle: string;
  eventLocation: string;
  /** `datetime-local` value: YYYY-MM-DDTHH:MM */
  eventStart: string;
  /** `datetime-local` value: YYYY-MM-DDTHH:MM */
  eventEnd: string;
  contactFirstName: string;
  contactLastName: string;
  contactOrg: string;
  contactJobTitle: string;
  contactPhonePrefix: string;
  contactPhoneNumber: string;
  contactEmail: string;
  contactWebsite: string;
  contactStreet: string;
  contactCity: string;
  contactPostal: string;
  contactCountry: string;
}

export type FieldName = keyof FormValues;

export function emptyValues(): FormValues {
  return {
    text: '',
    wifiName: '',
    wifiSecurity: 'WPA2',
    wifiPassword: '',
    emailAddress: '',
    emailAdvanced: false,
    emailSubject: '',
    emailBody: '',
    phonePrefix: '',
    phoneNumber: '',
    smsPrefix: '',
    smsNumber: '',
    smsMessage: '',
    latitude: '',
    longitude: '',
    eventTitle: '',
    eventLocation: '',
    eventStart: '',
    eventEnd: '',
    contactFirstName: '',
    contactLastName: '',
    contactOrg: '',
    contactJobTitle: '',
    contactPhonePrefix: '',
    contactPhoneNumber: '',
    contactEmail: '',
    contactWebsite: '',
    contactStreet: '',
    contactCity: '',
    contactPostal: '',
    contactCountry: '',
  };
}

const digits = (value: string) => value.replace(/[^\d]/g, '');

/** Escapes a value for the `WIFI:` scheme: \ ; , : and " need a backslash. */
export function wifiEscape(value: string): string {
  return value.replace(/([\\;,:"])/g, '\\$1');
}

/** Escapes a vCard TEXT value (RFC 2426 / 6350): \ ; , and newlines. */
export function vcardEscape(value: string): string {
  return value
    .trim()
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\n|\r/g, '\\n');
}

/** Escapes an iCalendar TEXT value (RFC 5545). */
export function icalEscape(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\n|\r/g, '\\n');
}

/** `2026-01-31T09:30` → `20260131T093000` (floating local time). */
export function icalDateTime(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(value);
  if (!match) return '';
  const [, y, mo, d, h, mi, s] = match;
  return `${y}${mo}${d}T${h}${mi}${s ?? '00'}`;
}

function phoneWithPrefix(prefix: string, number: string): string {
  const n = digits(number);
  if (!n) return '';
  const p = digits(prefix);
  return p ? `+${p}${n}` : n;
}

export function buildVcard(v: FormValues): string {
  const first = v.contactFirstName.trim();
  const last = v.contactLastName.trim();
  const fullName = [first, last].filter(Boolean).join(' ');
  const lines = [
    'BEGIN:VCARD',
    'VERSION:3.0',
    `N:${vcardEscape(last)};${vcardEscape(first)};;;`,
    `FN:${vcardEscape(fullName)}`,
  ];
  if (v.contactOrg.trim()) lines.push(`ORG:${vcardEscape(v.contactOrg)}`);
  if (v.contactJobTitle.trim()) lines.push(`TITLE:${vcardEscape(v.contactJobTitle)}`);
  const phone = phoneWithPrefix(v.contactPhonePrefix, v.contactPhoneNumber);
  if (phone) lines.push(`TEL;TYPE=CELL:${phone}`);
  if (v.contactEmail.trim()) lines.push(`EMAIL;TYPE=INTERNET:${v.contactEmail.trim()}`);
  if (v.contactWebsite.trim()) lines.push(`URL:${v.contactWebsite.trim()}`);
  const address = [v.contactStreet, v.contactCity, v.contactPostal, v.contactCountry];
  if (address.some((part) => part.trim())) {
    const [street, city, postal, country] = address.map(vcardEscape);
    lines.push(`ADR;TYPE=HOME:;;${street};${city};;${postal};${country}`);
  }
  lines.push('END:VCARD');
  return lines.join('\r\n');
}

export function buildEvent(v: FormValues): string {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'BEGIN:VEVENT',
    `SUMMARY:${icalEscape(v.eventTitle)}`,
    `LOCATION:${icalEscape(v.eventLocation)}`,
  ];
  const start = icalDateTime(v.eventStart);
  const end = icalDateTime(v.eventEnd);
  if (start) lines.push(`DTSTART:${start}`);
  if (end) lines.push(`DTEND:${end}`);
  lines.push('END:VEVENT', 'END:VCALENDAR');
  return lines.join('\r\n');
}

/** The exact text that ends up inside the QR code. */
export function buildPayload(type: QrType, v: FormValues): string {
  switch (type) {
    case 'text':
      return v.text;
    case 'wifi': {
      const ssid = wifiEscape(v.wifiName);
      if (v.wifiSecurity === 'nopass') return `WIFI:S:${ssid};T:nopass;;`;
      return `WIFI:S:${ssid};T:${v.wifiSecurity};P:${wifiEscape(v.wifiPassword)};;`;
    }
    case 'email': {
      const address = v.emailAddress.trim();
      if (!v.emailAdvanced) return `mailto:${address}`;
      const params: string[] = [];
      if (v.emailSubject) params.push(`subject=${encodeURIComponent(v.emailSubject)}`);
      if (v.emailBody) params.push(`body=${encodeURIComponent(v.emailBody)}`);
      return `mailto:${address}${params.length ? `?${params.join('&')}` : ''}`;
    }
    case 'phone':
      return `tel:+${digits(v.phonePrefix)}${digits(v.phoneNumber)}`;
    case 'sms':
      return `SMSTO:+${digits(v.smsPrefix)}${digits(v.smsNumber)}:${v.smsMessage}`;
    case 'location':
      return `geo:${v.latitude.trim()},${v.longitude.trim()}`;
    case 'event':
      return buildEvent(v);
    case 'contact':
      return buildVcard(v);
  }
}

/** True once the user has typed something meaningful for the type. */
export function hasContent(type: QrType, v: FormValues): boolean {
  switch (type) {
    case 'text':
      return v.text.length > 0;
    case 'wifi':
      return v.wifiName.length > 0;
    case 'email':
      return v.emailAddress.trim().length > 0;
    case 'phone':
      return digits(v.phoneNumber).length > 0;
    case 'sms':
      return digits(v.smsNumber).length > 0 || v.smsMessage.length > 0;
    case 'location':
      return v.latitude.trim().length > 0 || v.longitude.trim().length > 0;
    case 'event':
      return v.eventTitle.trim().length > 0 || v.eventLocation.trim().length > 0;
    case 'contact':
      return [
        v.contactFirstName, v.contactLastName, v.contactOrg, v.contactJobTitle,
        v.contactPhoneNumber, v.contactEmail, v.contactWebsite, v.contactStreet,
        v.contactCity, v.contactPostal, v.contactCountry,
      ].some((value) => value.trim().length > 0);
  }
}

export interface FieldError {
  field: FieldName;
  message: string;
}

const isCoordinate = (value: string, limit: number) => {
  if (!/^[-+]?\d+(\.\d+)?$/.test(value.trim())) return false;
  return Math.abs(Number(value)) <= limit;
};

/** Required-field checks, matching the QuickeR creator. */
export function validate(type: QrType, v: FormValues): FieldError[] {
  const errors: FieldError[] = [];
  const required = (field: FieldName, ok: boolean, message = 'Required') => {
    if (!ok) errors.push({ field, message });
  };
  switch (type) {
    case 'text':
      required('text', v.text.length > 0);
      break;
    case 'wifi':
      required('wifiName', v.wifiName.length > 0);
      if (v.wifiSecurity !== 'nopass') required('wifiPassword', v.wifiPassword.length > 0);
      break;
    case 'email':
      required('emailAddress', v.emailAddress.trim().length > 0);
      break;
    case 'phone':
      required('phonePrefix', digits(v.phonePrefix).length > 0);
      required('phoneNumber', digits(v.phoneNumber).length > 0);
      break;
    case 'sms':
      required('smsPrefix', digits(v.smsPrefix).length > 0);
      required('smsNumber', digits(v.smsNumber).length > 0);
      required('smsMessage', v.smsMessage.length > 0);
      break;
    case 'location':
      required('latitude', isCoordinate(v.latitude, 90), 'Enter a latitude between -90 and 90');
      required('longitude', isCoordinate(v.longitude, 180), 'Enter a longitude between -180 and 180');
      break;
    case 'event':
      required('eventTitle', v.eventTitle.trim().length > 0);
      required('eventLocation', v.eventLocation.trim().length > 0);
      required('eventStart', icalDateTime(v.eventStart) !== '');
      required('eventEnd', icalDateTime(v.eventEnd) !== '');
      if (v.eventStart && v.eventEnd && v.eventEnd < v.eventStart) {
        errors.push({ field: 'eventEnd', message: 'The end must be after the start' });
      }
      break;
    case 'contact': {
      const named = v.contactFirstName.trim().length > 0 || v.contactLastName.trim().length > 0;
      required('contactFirstName', named, 'A first or last name is required');
      break;
    }
  }
  return errors;
}

export function sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|']/g, '').trim();
}
