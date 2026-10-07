import { jest } from '@jest/globals';
import { VoiceAnnouncer, isVoiceEnabled, setVoiceEnabled, toggleVoice, announce, cancelSpeech } from '../static/js/modules/ui/voice_announcer.js';

describe('VoiceAnnouncer engine', () => {
    let mockSpeak;
    let mockCancel;

    beforeEach(() => {
        localStorage.clear();
        mockSpeak = jest.fn();
        mockCancel = jest.fn();

        globalThis.speechSynthesis = {
            speak: mockSpeak,
            cancel: mockCancel,
            getVoices: () => [
                { lang: 'zh-TW', name: 'Chinese Taiwan' },
                { lang: 'en-US', name: 'English US' },
            ],
        };

        globalThis.SpeechSynthesisUtterance = class {
            constructor(text) {
                this.text = text;
                this.lang = 'en-US';
                this.rate = 1;
                this.pitch = 1;
            }
        };
    });

    afterEach(() => {
        delete globalThis.speechSynthesis;
        delete globalThis.SpeechSynthesisUtterance;
    });

    test('isVoiceEnabled defaults to true and respects storage', () => {
        expect(isVoiceEnabled()).toBe(true);

        setVoiceEnabled(false);
        expect(isVoiceEnabled()).toBe(false);
        expect(localStorage.getItem('smart_chess_voice_enabled')).toBe('false');

        toggleVoice();
        expect(isVoiceEnabled()).toBe(true);
        expect(localStorage.getItem('smart_chess_voice_enabled')).toBe('true');
    });

    test('announce calls speechSynthesis with zh-TW utterance when enabled', () => {
        setVoiceEnabled(true);
        const spoken = announce('輪到紅方移動');
        expect(spoken).toBe(true);
        expect(mockSpeak).toHaveBeenCalledTimes(1);

        const utterance = mockSpeak.mock.calls[0][0];
        expect(utterance.text).toBe('輪到紅方移動');
        expect(utterance.lang).toBe('zh-TW');
    });

    test('announce suppresses speech when voice is muted', () => {
        setVoiceEnabled(false);
        const spoken = announce('測試訊息');
        expect(spoken).toBe(false);
        expect(mockSpeak).not.toHaveBeenCalled();
    });

    test('announce suppresses rapid duplicate speech', () => {
        setVoiceEnabled(true);
        const first = announce('重複提示訊息');
        expect(first).toBe(true);
        expect(mockSpeak).toHaveBeenCalledTimes(1);

        // Immediate duplicate
        const second = announce('重複提示訊息');
        expect(second).toBe(false);
        expect(mockSpeak).toHaveBeenCalledTimes(1);

        // Forced duplicate works
        const third = announce('重複提示訊息', { force: true });
        expect(third).toBe(true);
        expect(mockSpeak).toHaveBeenCalledTimes(2);
    });

    test('priority announcement cancels ongoing speech first', () => {
        setVoiceEnabled(true);
        announce('緊急警告，手臂動作中！', { priority: true });
        expect(mockCancel).toHaveBeenCalledTimes(1);
        expect(mockSpeak).toHaveBeenCalledTimes(1);
    });

    test('cancelSpeech delegates to speechSynthesis.cancel', () => {
        cancelSpeech();
        expect(mockCancel).toHaveBeenCalledTimes(1);
    });
});
