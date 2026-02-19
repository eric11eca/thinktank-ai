import { math } from "@streamdown/math";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import type { StreamdownProps } from "streamdown";

import { rehypeSplitWordsIntoSpans } from "../rehype";

export const streamdownPlugins = {
  remarkPlugins: [
    remarkGfm,
    math.remarkPlugin,
  ] as StreamdownProps["remarkPlugins"],
  rehypePlugins: [
    rehypeRaw,
    math.rehypePlugin,
  ] as StreamdownProps["rehypePlugins"],
};

export const streamdownPluginsWithWordAnimation = {
  remarkPlugins: [
    remarkGfm,
    math.remarkPlugin,
  ] as StreamdownProps["remarkPlugins"],
  rehypePlugins: [
    math.rehypePlugin,
    rehypeSplitWordsIntoSpans,
  ] as StreamdownProps["rehypePlugins"],
};

// Plugins for human messages - no autolink to prevent URL bleeding into adjacent text
export const humanMessagePlugins = {
  remarkPlugins: [
    // Use remark-gfm without autolink literals by not including it
    // Only include math support for human messages
    math.remarkPlugin,
  ] as StreamdownProps["remarkPlugins"],
  rehypePlugins: [
    math.rehypePlugin,
  ] as StreamdownProps["rehypePlugins"],
};
