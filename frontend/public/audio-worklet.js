// AudioWorkletProcessor — 마이크 입력을 16kHz mono PCM16으로 다운샘플링 후 메인 스레드로 전달.
class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = (options.processorOptions && options.processorOptions.targetRate) || 16000;
    this.inputRate = sampleRate;
    this.ratio = this.inputRate / this.targetRate;
    this.acc = 0;
    this.buf = [];
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    // 다운샘플링 (interpolation 없는 간단 추출)
    for (let i = 0; i < channel.length; i++) {
      this.acc += 1;
      if (this.acc >= this.ratio) {
        this.acc -= this.ratio;
        // float32(-1..1) → int16
        let s = channel[i];
        s = Math.max(-1, Math.min(1, s));
        this.buf.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      }
    }

    // ~20ms(=320 samples)마다 메인으로 전송
    while (this.buf.length >= 320) {
      const out = new Int16Array(this.buf.splice(0, 320));
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}

registerProcessor('mic-capture', MicCaptureProcessor);
