import React from 'react';
import {
  AbsoluteFill,
  Img,
  Easing,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const C = {
  bg0: '#050816',
  bg1: '#0B1640',
  teal: '#006B72',
  cyan: '#00A7B5',
  red: '#F5265D',
  green: '#238C68',
  white: '#F7F8FB',
  muted: '#AAB1C2',
  line: '#2E3545',
  card: '#171B25',
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
const I = (frame, input, output, easing = Easing.inOut(Easing.cubic)) =>
  interpolate(frame, input, output, {...clamp, easing});

const Brand = ({scale = 1, showAsset = true, opacity = 1}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: 14 * scale, opacity}}>
    {showAsset ? (
      <Img
        src={staticFile('dsh-logo.png')}
        style={{height: 54 * scale, width: 260 * scale, objectFit: 'contain'}}
      />
    ) : (
      <>
        <div style={{position: 'relative', width: 30 * scale, height: 42 * scale}}>
          <div style={{position: 'absolute', left: 10 * scale, top: 0, width: 8 * scale, height: 42 * scale, background: C.red, transform: 'skew(-11deg)', borderRadius: 5 * scale}} />
          <div style={{position: 'absolute', left: 0, top: 10 * scale, width: 19 * scale, height: 19 * scale, border: `${5 * scale}px solid ${C.red}`, borderRightColor: 'transparent', borderBottomColor: 'transparent', transform: 'rotate(-42deg)', borderRadius: '50%'}} />
        </div>
        <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: C.white, fontSize: 28 * scale, fontWeight: 700, letterSpacing: -0.7 * scale}}>InteractiveBrokers</div>
      </>
    )}
  </div>
);

const Choice = ({label, tone = 'neutral', selected = false}) => {
  const bg = tone === 'green' ? '#165C48' : tone === 'red' ? '#602638' : '#222733';
  const dot = tone === 'green' ? '#6AE5B3' : tone === 'red' ? '#FF7F9A' : '#D4D7DE';
  return (
    <div style={{height: 69, borderRadius: 15, padding: '0 18px', display: 'flex', alignItems: 'center', gap: 14, background: bg, border: selected ? `2px solid ${dot}` : '1px solid #333A49', boxShadow: selected ? `0 0 0 3px ${dot}18` : 'none'}}>
      <div style={{width: 16, height: 16, borderRadius: 99, background: dot, boxShadow: `0 0 16px ${dot}66`}} />
      <span style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#F3F4F7', fontSize: 22, fontWeight: 600}}>{label}</span>
    </div>
  );
};

const StrategyRow = ({name, price, positive = false, delay = 0, frame = 0}) => {
  const p = I(frame, [302 + delay, 320 + delay], [0, 1], Easing.out(Easing.cubic));
  return (
    <div style={{height: 95, borderRadius: 16, background: '#1A1E28', border: '1px solid #303646', padding: '13px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', opacity: p, transform: `translateY(${(1 - p) * 24}px)`}}>
      <div>
        <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#F4F5F7', fontSize: 18, fontWeight: 650}}>{name}</div>
        <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#7F8799', fontSize: 14, marginTop: 7}}>Strategy details</div>
      </div>
      <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: positive ? '#B7F5CE' : '#FFD0D9', fontSize: 25, fontWeight: 800}}>{price}</div>
    </div>
  );
};

const Phone = ({frame, x = 540, y = 520, scale = 1}) => {
  const strategyMix = I(frame, [292, 322], [0, 1]);
  const questionMix = 1 - strategyMix;
  const selectedPulse = I(frame, [108, 122, 138], [0, 1, 0], Easing.inOut(Easing.ease));
  return (
    <div style={{position: 'absolute', left: x, top: y, width: 500, height: 970, transform: `translateX(-50%) scale(${scale})`, transformOrigin: 'top center', filter: 'drop-shadow(0 28px 50px rgba(0,0,0,.50))'}}>
      <div style={{position: 'absolute', inset: 0, borderRadius: 62, background: '#11151F', border: '3px solid #515969', boxShadow: 'inset 0 0 0 3px #07090F, 0 30px 80px rgba(0,0,0,.35)'}} />
      <div style={{position: 'absolute', left: 18, right: 18, top: 18, bottom: 18, borderRadius: 50, overflow: 'hidden', background: '#0D1018'}}>
        <div style={{position: 'absolute', top: 14, left: '50%', width: 126, height: 24, borderRadius: 99, background: '#1C2029', transform: 'translateX(-50%)'}} />
        <div style={{position: 'absolute', left: 31, right: 31, top: 66}}>
          <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#8F96A6', fontSize: 18}}>TSLA</div>
          <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: C.white, fontSize: 34, fontWeight: 760, marginTop: 8}}>TSLA Options</div>
        </div>

        <div style={{position: 'absolute', left: 31, right: 31, top: 160, opacity: questionMix, transform: `translateX(${-24 * strategyMix}px)`}}>
          <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#B2B7C4', fontSize: 19, lineHeight: 1.25, marginBottom: 18}}>What is your prediction for TSLA?</div>
          <div style={{display: 'grid', gap: 12}}>
            <Choice label="TSLA price will go up" tone="green" selected={selectedPulse > 0.5} />
            <Choice label="TSLA price will go down" tone="red" />
            <Choice label="Price will stay flat" />
            <Choice label="Risk level is moderate" />
          </div>
          <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#5F6776', fontSize: 14, marginTop: 20, lineHeight: 1.35}}>Use forecast tools to explore potential outcomes before you trade.</div>
        </div>

        <div style={{position: 'absolute', left: 31, right: 31, top: 154, opacity: strategyMix, transform: `translateX(${22 * questionMix}px)`}}>
          <StrategyRow frame={frame} delay={0} name="Jun 05 535 Short Put" price="-$8.75" />
          <div style={{height: 10}} />
          <StrategyRow frame={frame} delay={5} name="Jun 05 530 Short Put" price="-$18.40" />
          <div style={{height: 10}} />
          <StrategyRow frame={frame} delay={10} name="Jun 05 375/345 Bull Put" price="+$141.35" positive />
          <div style={{height: 10}} />
          <StrategyRow frame={frame} delay={15} name="Jun 05 435/375 Bull Call" price="+$18.90" positive />
        </div>
      </div>
    </div>
  );
};

const FloatingCard = ({frame, inFrame, outFrame, fromX, toX, y, width = 470, children, light = false, rotate = 0}) => {
  const enter = I(frame, [inFrame, inFrame + 18], [0, 1], Easing.out(Easing.cubic));
  const exit = I(frame, [outFrame - 15, outFrame], [1, 0], Easing.in(Easing.cubic));
  const p = Math.min(enter, exit);
  const x = fromX + (toX - fromX) * enter + (1 - exit) * (toX > 540 ? 80 : -80);
  return (
    <div style={{position: 'absolute', left: x, top: y, width, transform: `translateX(-50%) translateY(${(1-p)*20}px) rotate(${rotate * p}deg)`, opacity: p, borderRadius: 28, background: light ? 'rgba(250,251,253,.98)' : 'rgba(22,25,34,.97)', border: light ? '1px solid #DCE0E8' : '1px solid #434B5D', boxShadow: '0 24px 60px rgba(0,0,0,.38)', padding: light ? '30px 30px 34px' : '23px 24px'}}>
      {children}
    </div>
  );
};

const BullishCard = ({frame}) => (
  <FloatingCard frame={frame} inFrame={145} outFrame={207} fromX={-250} toX={360} y={790} width={470} rotate={-1.5}>
    <div style={{display: 'flex', alignItems: 'center', gap: 15}}>
      <div style={{width: 44, height: 44, borderRadius: 11, display: 'grid', placeItems: 'center', background: '#202530', color: C.red, fontSize: 26, fontWeight: 900}}>T</div>
      <div>
        <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: C.white, fontSize: 24, fontWeight: 750}}>You're bullish on TSLA</div>
        <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: C.muted, fontSize: 16, marginTop: 5}}>Predicting TSLA may rise.</div>
      </div>
    </div>
  </FloatingCard>
);

const PercentCard = ({frame}) => (
  <FloatingCard frame={frame} inFrame={188} outFrame={257} fromX={1310} toX={725} y={850} width={410} rotate={1.4}>
    <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#F0F2F6', fontSize: 18, lineHeight: 1.25}}>I think the price of TSLA will go...</div>
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'baseline', gap: 10, marginTop: 15}}>
      <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: C.white, fontSize: 63, fontWeight: 850}}>7%</div>
      <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#818899', fontSize: 16}}>to 5395.93</div>
    </div>
  </FloatingCard>
);

const TimeCard = ({frame}) => (
  <FloatingCard frame={frame} inFrame={242} outFrame={310} fromX={540} toX={540} y={850} width={430} light rotate={0}>
    <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#222735', fontSize: 24, fontWeight: 800, textAlign: 'center'}}>Time Horizon</div>
    <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#697083', fontSize: 17, lineHeight: 1.35, textAlign: 'center', marginTop: 18}}>When do you expect the price of TSLA to meet your forecast?</div>
    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 24}}>
      <div style={{borderRadius: 13, background: '#EEF1F5', color: '#303544', padding: '12px 0', textAlign: 'center', fontFamily: 'Arial, Helvetica, sans-serif', fontSize: 15, fontWeight: 700}}>1–7 days</div>
      <div style={{borderRadius: 13, background: '#EEF1F5', color: '#303544', padding: '12px 0', textAlign: 'center', fontFamily: 'Arial, Helvetica, sans-serif', fontSize: 15, fontWeight: 700}}>1–4 weeks</div>
    </div>
  </FloatingCard>
);

const Headline = ({frame}) => {
  const first = I(frame, [8, 24, 66, 83], [0, 1, 1, 0]);
  const second = I(frame, [64, 81, 111, 126], [0, 1, 1, 0]);
  const strategy = I(frame, [306, 326, 369, 386], [0, 1, 1, 0]);
  return (
    <>
      <div style={{position: 'absolute', top: 290, left: 120, right: 120, textAlign: 'center', opacity: first, transform: `translateY(${(1-first)*18}px)`, fontFamily: 'Georgia, Times New Roman, serif', color: C.white, fontSize: 78, lineHeight: 1.06, letterSpacing: -2}}>New to trading<br/>options spreads?</div>
      <div style={{position: 'absolute', top: 304, left: 120, right: 120, textAlign: 'center', opacity: second, transform: `translateY(${(1-second)*18}px)`, fontFamily: 'Georgia, Times New Roman, serif', color: C.white, fontSize: 77, lineHeight: 1.06, letterSpacing: -2}}>Get started with<br/>confidence</div>
      <div style={{position: 'absolute', top: 260, left: 100, right: 100, textAlign: 'center', opacity: strategy, transform: `translateY(${(1-strategy)*18}px)`, fontFamily: 'Georgia, Times New Roman, serif', color: C.white, fontSize: 80, lineHeight: 1.06, letterSpacing: -2}}>Option strategies<br/>simplified</div>
    </>
  );
};

export const IBKRRecreate = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const phoneIntro = spring({frame, fps, from: 0, to: 1, config: {damping: 18, mass: 0.75, stiffness: 120}});
  const phoneExit = I(frame, [374, 426], [0, 1], Easing.inOut(Easing.cubic));
  const phoneY = 555 - 30 * phoneIntro + 160 * phoneExit;
  const phoneScale = 0.94 + 0.06 * phoneIntro - 0.08 * phoneExit;
  const brandProof = I(frame, [380, 405], [0, 1], Easing.out(Easing.cubic));
  const openAccount = I(frame, [396, 420], [0, 1], Easing.out(Easing.cubic));
  const bgShift = I(frame, [0, 447], [0, 1], Easing.linear);

  return (
    <AbsoluteFill style={{background: C.bg0, overflow: 'hidden'}}>
      <AbsoluteFill style={{background: `radial-gradient(circle at ${28 + bgShift*8}% ${74 - bgShift*4}%, rgba(0,167,181,.72) 0%, rgba(0,107,114,.33) 25%, transparent 55%), radial-gradient(circle at 72% 24%, rgba(36,67,167,.56) 0%, transparent 55%), linear-gradient(180deg, #050719 0%, #07112D 48%, #06111B 100%)`}} />
      <AbsoluteFill style={{background: 'radial-gradient(circle at center, transparent 35%, rgba(0,0,0,.42) 100%)'}} />

      <div style={{position: 'absolute', top: 92, left: 0, right: 0, display: 'flex', justifyContent: 'center', opacity: I(frame, [0, 18, 372, 392], [0, 1, 1, .45])}}>
        <Brand scale={0.86} />
      </div>

      <Headline frame={frame} />

      <Phone frame={frame} y={phoneY} scale={phoneScale} />
      <BullishCard frame={frame} />
      <PercentCard frame={frame} />
      <TimeCard frame={frame} />

      <div style={{position: 'absolute', top: 170, left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20, opacity: brandProof, transform: `translateY(${(1-brandProof)*20}px)`}}>
        <div style={{fontFamily: 'Arial, Helvetica, sans-serif', color: '#D9DDE8', fontSize: 22, fontWeight: 760, letterSpacing: 3.2}}>THE BEST INFORMED INVESTORS CHOOSE</div>
        <Brand scale={1.28} />
        <div style={{height: 66, padding: '0 28px', minWidth: 240, borderRadius: 40, display: 'grid', placeItems: 'center', background: C.red, color: 'white', fontFamily: 'Arial, Helvetica, sans-serif', fontSize: 24, fontWeight: 800, opacity: openAccount, transform: `scale(${.88 + .12*openAccount})`}}>Open Account →</div>
      </div>

      <div style={{position: 'absolute', left: 80, right: 80, bottom: 78, textAlign: 'center', color: '#A4ABBA', fontFamily: 'Arial, Helvetica, sans-serif', fontSize: 18, lineHeight: 1.35, opacity: I(frame, [100, 130], [0, .86])}}>Options involve risk. Multiple leg strategies may incur multiple commissions. For more information, visit ibkr.com.</div>
    </AbsoluteFill>
  );
};
