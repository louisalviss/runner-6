import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {IBKRRecreate} from './IBKR';

const Root = () => (
  <Composition
    id="IBKRRecreate"
    component={IBKRRecreate}
    durationInFrames={447}
    fps={30}
    width={1080}
    height={1920}
  />
);

registerRoot(Root);
