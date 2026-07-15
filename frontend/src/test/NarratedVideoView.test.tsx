import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NarratedVideoView } from "../features/node-details/ResourcePanel";

describe("NarratedVideoView", () => {
  it("renders the MP4 player, captions and generation metadata", () => {
    const { container } = render(
      <NarratedVideoView
        pathId="path-1"
        nodeId="node-1"
        content={{
          duration_seconds: 92,
          slide_count: 7,
          tts_model: "FunAudioLLM/CosyVoice2-0.5B",
          captions_vtt: "WEBVTT\n\n00:00:00.000 --> 00:00:03.000\n欢迎学习",
        }}
      />,
    );

    const video = container.querySelector("video");
    const source = container.querySelector("source");
    const track = container.querySelector("track");
    expect(video).toHaveAttribute("controls");
    expect(source).toHaveAttribute(
      "src",
      "/api/learning-paths/path-1/nodes/node-1/resources/narrated_video/download",
    );
    expect(track?.getAttribute("src")).toContain("data:text/vtt");
    expect(track).not.toHaveAttribute("default");
    expect(video).toHaveClass("narrated-course");
    expect(screen.getByText("1:32")).toBeInTheDocument();
    expect(screen.getByText("7 页")).toBeInTheDocument();
    expect(screen.getByText("FunAudioLLM/CosyVoice2-0.5B")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "下载 MP4 讲解视频" })).toHaveAttribute(
      "href",
      "/api/learning-paths/path-1/nodes/node-1/resources/narrated_video/download",
    );
  });
});
