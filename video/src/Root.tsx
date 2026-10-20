import React from "react";
import { Composition } from "remotion";
import { Demo, TOTAL } from "./Demo";

export const RemotionRoot: React.FC = () => (
  <Composition id="Demo" component={Demo} durationInFrames={TOTAL} fps={30} width={1920} height={1080} />
);
