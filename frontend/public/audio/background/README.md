# EFHC background music — OWNER single-track canon (Cycle0558 iteration02)

The **only** background composition is `1.mp3` (58 seconds, MPEG Layer III, stereo, LAME VBR q5). OWNER explicitly chose MP3-only compatibility and one permanent track. No extra tracks or placeholder sounds are authorized. `playlist.json` is retained for compatibility and contains only `1.mp3`; `npm run music:playlist` regenerates it if needed.

Music is OFF by default. When enabled, React requests `/audio/background/1.mp3`, decodes it **once** with Web Audio `decodeAudioData`, and loops the entire PCM buffer with `AudioBufferSourceNode.loop`. It is NOT repeatedly loaded as an HTML audio element, because that path can cause an audible ~0.5s gap on some devices. The user toggle primes AudioContext synchronously for browser autoplay policy; a later real gesture may unlock persisted ON state. When OFF, playback stops, loading is aborted and the context is closed. No audio request/decoding while OFF.

The standalone `FRONTEND_v859.html` embeds the same compact MP3 as a base64 data URI. Therefore the HTML file includes the audio bytes even when music is OFF, but does not decode or play them until ON. Its audio is likewise a looping PCM buffer, not an HTMLAudioElement. The separate OGG master was used only to create MP3, and is not included in the user release.

Protected: the language carousel and 10 CT visuals are out of scope and must remain unchanged.
