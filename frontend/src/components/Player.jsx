// Media player that can jump to any second.
// - YouTube lessons use the official IFrame Player API (the video is streamed, never downloaded)
// - Uploaded recordings use the browser's <audio>/<video>
// Parent components call ref.current.seek(seconds) and ref.current.currentTime().
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

let ytReady; // one shared promise for loading the YouTube script
function loadYouTubeApi() {
  if (!ytReady) {
    ytReady = new Promise((resolve) => {
      if (window.YT?.Player) return resolve(window.YT);
      window.onYouTubeIframeAPIReady = () => resolve(window.YT);
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(s);
    });
  }
  return ytReady;
}

const Player = forwardRef(function Player({ youtubeId, mediaUrl, mediaKind }, ref) {
  const holder = useRef(null);   // div replaced by the YouTube iframe
  const yt = useRef(null);       // YT.Player instance
  const media = useRef(null);    // <audio>/<video> element

  useEffect(() => {
    if (!youtubeId) return;
    let cancelled = false;
    loadYouTubeApi().then((YT) => {
      if (cancelled || !holder.current) return;
      // Give YouTube its own element to replace, so React's DOM stays intact
      const el = document.createElement("div");
      holder.current.appendChild(el);
      yt.current = new YT.Player(el, {
        videoId: youtubeId,
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
      });
    });
    return () => {
      cancelled = true;
      yt.current?.destroy?.();
      yt.current = null;
      if (holder.current) holder.current.innerHTML = "";
    };
  }, [youtubeId]);

  useImperativeHandle(ref, () => ({
    seek(seconds) {
      if (yt.current?.seekTo) {
        yt.current.seekTo(seconds, true);
        yt.current.playVideo();
      } else if (media.current) {
        media.current.currentTime = seconds;
        media.current.play();
      }
    },
    currentTime() {
      if (yt.current?.getCurrentTime) return yt.current.getCurrentTime();
      return media.current?.currentTime || 0;
    },
    hasMedia: () => Boolean(youtubeId || mediaUrl),
  }));

  if (youtubeId)
    return (
      <div className="player video">
        <div ref={holder} />
      </div>
    );
  if (mediaUrl) {
    const isVideo = mediaKind === "video";
    return (
      <div className="player">
        {isVideo ? (
          <video ref={media} src={mediaUrl} controls playsInline />
        ) : (
          <audio ref={media} src={mediaUrl} controls />
        )}
      </div>
    );
  }
  return null;
});

export default Player;
