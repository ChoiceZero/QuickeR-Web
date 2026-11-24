import { describe, expect, it } from 'vitest';
import { buildPayload, emptyValues, sanitizeFilename, validate, type FormValues } from './payload';
import { contrastLevel } from './color';

const values = (overrides: Partial<FormValues>): FormValues => ({ ...emptyValues(), ...overrides });

describe('buildPayload', () => {
  it('encodes text and links as-is', () => {
    expect(buildPayload('text', values({ text: 'https://example.com' }))).toBe('https://example.com');
  });

  it('encodes Wi-Fi networks, escaping special characters', () => {
    expect(buildPayload('wifi', values({ wifiName: 'Home;Net', wifiSecurity: 'WPA2', wifiPassword: 'p:w"d' })))
      .toBe('WIFI:S:Home\\;Net;T:WPA2;P:p\\:w\\"d;;');
    expect(buildPayload('wifi', values({ wifiName: 'Cafe', wifiSecurity: 'nopass', wifiPassword: 'ignored' })))
      .toBe('WIFI:S:Cafe;T:nopass;;');
  });

  it('encodes email with optional subject and body', () => {
    expect(buildPayload('email', values({ emailAddress: 'a@b.c' }))).toBe('mailto:a@b.c');
    expect(buildPayload('email', values({ emailAddress: 'a@b.c', emailSubject: 'Hi there' }))).toBe('mailto:a@b.c');
    expect(buildPayload('email', values({ emailAddress: 'a@b.c', emailAdvanced: true, emailSubject: 'Hi there', emailBody: 'x&y' })))
      .toBe('mailto:a@b.c?subject=Hi%20there&body=x%26y');
  });

  it('encodes phone and SMS with the country prefix', () => {
    expect(buildPayload('phone', values({ phonePrefix: '34', phoneNumber: '600 11 22 33' }))).toBe('tel:+34600112233');
    expect(buildPayload('sms', values({ smsPrefix: '34', smsNumber: '600112233', smsMessage: 'Hello' })))
      .toBe('SMSTO:+34600112233:Hello');
  });

  it('encodes locations', () => {
    expect(buildPayload('location', values({ latitude: '43.035', longitude: '-2.77988' }))).toBe('geo:43.035,-2.77988');
  });

  it('encodes events as iCalendar', () => {
    const payload = buildPayload('event', values({
      eventTitle: 'Launch, party', eventLocation: 'Bilbao', eventStart: '2026-01-31T09:30', eventEnd: '2026-01-31T11:00',
    }));
    expect(payload).toBe([
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'BEGIN:VEVENT', 'SUMMARY:Launch\\, party', 'LOCATION:Bilbao',
      'DTSTART:20260131T093000', 'DTEND:20260131T110000', 'END:VEVENT', 'END:VCALENDAR',
    ].join('\r\n'));
  });

  it('encodes contacts as vCard 3.0, omitting empty fields', () => {
    const payload = buildPayload('contact', values({
      contactFirstName: 'Ana', contactLastName: 'García', contactOrg: 'ACME; Inc',
      contactPhonePrefix: '34', contactPhoneNumber: '600112233', contactCity: 'Bilbao',
    }));
    expect(payload).toBe([
      'BEGIN:VCARD', 'VERSION:3.0', 'N:García;Ana;;;', 'FN:Ana García', 'ORG:ACME\\; Inc',
      'TEL;TYPE=CELL:+34600112233', 'ADR;TYPE=HOME:;;;Bilbao;;;', 'END:VCARD',
    ].join('\r\n'));
  });
});

describe('validate', () => {
  it('requires a password unless the network is open', () => {
    expect(validate('wifi', values({ wifiName: 'Net' })).map((e) => e.field)).toEqual(['wifiPassword']);
    expect(validate('wifi', values({ wifiName: 'Net', wifiSecurity: 'nopass' }))).toEqual([]);
  });

  it('checks coordinate ranges', () => {
    expect(validate('location', values({ latitude: '91', longitude: 'abc' })).map((e) => e.field))
      .toEqual(['latitude', 'longitude']);
    expect(validate('location', values({ latitude: '43.035', longitude: '-2.77' }))).toEqual([]);
  });

  it('requires a first or last name for contacts', () => {
    expect(validate('contact', values({}))).toHaveLength(1);
    expect(validate('contact', values({ contactLastName: 'García' }))).toEqual([]);
  });

  it('rejects events that end before they start', () => {
    const errors = validate('event', values({
      eventTitle: 'A', eventLocation: 'B', eventStart: '2026-01-31T10:00', eventEnd: '2026-01-31T09:00',
    }));
    expect(errors.map((e) => e.field)).toEqual(['eventEnd']);
  });
});

describe('helpers', () => {
  it('strips characters that are invalid in filenames', () => {
    expect(sanitizeFilename(' my/qr:"code" ')).toBe('myqrcode');
  });

  it('rates color contrast like the QuickeR app', () => {
    expect(contrastLevel('#000000', '#ffffff')).toBe('ok');
    expect(contrastLevel('#777777', '#aaaaaa')).toBe('low');
  });
});
