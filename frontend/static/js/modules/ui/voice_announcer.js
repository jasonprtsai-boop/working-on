/**
 * voice_announcer.js - Web Speech API Voice Prompt Engine
 *
 * Provides real-time speech guidance for human-robot interaction (HRI).
 * Announces turn changes, vision scanning hints, safety warnings, and game outcomes.
 */

const STORAGE_KEY = 'smart_chess_voice_enabled';
const REPEAT_SUPPRESS_MS = 6000;

let lastSpokenText = '';
let lastSpokenTimestamp = 0;

function getStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

export function isVoiceEnabled() {
    const storage = getStorage();
    if (!storage) return true;
    const value = storage.getItem(STORAGE_KEY);
    return value === null ? true : value === 'true';
}

export function setVoiceEnabled(enabled) {
    const storage = getStorage();
    const boolVal = Boolean(enabled);
    if (storage) {
        storage.setItem(STORAGE_KEY, String(boolVal));
    }
    return boolVal;
}

export function toggleVoice() {
    const nextState = !isVoiceEnabled();
    setVoiceEnabled(nextState);
    if (nextState) {
        announce('語音播報已開啟', { force: true });
    }
    return nextState;
}

export function cancelSpeech() {
    const synth = globalThis.speechSynthesis;
    if (synth && typeof synth.cancel === 'function') {
        synth.cancel();
    }
}

export function announce(text, { priority = false, force = false } = {}) {
    const cleanText = String(text || '').trim();
    if (!cleanText) return false;

    if (!isVoiceEnabled() && !force) {
        return false;
    }

    const synth = globalThis.speechSynthesis;
    if (!synth || typeof synth.speak !== 'function') {
        return false;
    }

    const now = Date.now();
    if (!force && !priority && cleanText === lastSpokenText && now - lastSpokenTimestamp < REPEAT_SUPPRESS_MS) {
        return false;
    }

    if (priority && typeof synth.cancel === 'function') {
        synth.cancel();
    }

    try {
        if (typeof globalThis.SpeechSynthesisUtterance !== 'function') {
            return false;
        }

        const utterance = new globalThis.SpeechSynthesisUtterance(cleanText);
        utterance.lang = 'zh-TW';
        utterance.rate = 1.05;
        utterance.pitch = 1.0;

        if (typeof synth.getVoices === 'function') {
            const voices = synth.getVoices() || [];
            const zhVoice = voices.find(v => v.lang === 'zh-TW' || v.lang === 'zh-HK')
                || voices.find(v => v.lang?.startsWith('zh'));
            if (zhVoice) {
                utterance.voice = zhVoice;
            }
        }

        lastSpokenText = cleanText;
        lastSpokenTimestamp = now;
        synth.speak(utterance);
        return true;
    } catch {
        return false;
    }
}

export const VoiceAnnouncer = {
    isVoiceEnabled,
    setVoiceEnabled,
    toggleVoice,
    announce,
    cancelSpeech,
};
