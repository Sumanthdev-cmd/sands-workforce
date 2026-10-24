import { useEffect, useRef, useState } from "react";

export default function SignaturePad({ value, onChange, label = "Optional signature" }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const [hasInk, setHasInk] = useState(Boolean(value));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !value) return;
    const image = new Image();
    image.onload = () => {
      const context = canvas.getContext("2d");
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
    };
    image.src = value;
  }, [value]);

  function point(event) {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height),
    };
  }

  function start(event) {
    drawing.current = true;
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    const p = point(event);
    context.beginPath();
    context.moveTo(p.x, p.y);
    canvas.setPointerCapture?.(event.pointerId);
  }

  function move(event) {
    if (!drawing.current) return;
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    const p = point(event);
    context.lineWidth = 2.2;
    context.lineCap = "round";
    context.strokeStyle = "#172033";
    context.lineTo(p.x, p.y);
    context.stroke();
    setHasInk(true);
  }

  function end() {
    if (!drawing.current) return;
    drawing.current = false;
    const canvas = canvasRef.current;
    if (hasInk || canvas) onChange(canvas.toDataURL("image/png"));
  }

  function clear() {
    const canvas = canvasRef.current;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    setHasInk(false);
    onChange(null);
  }

  return (
    <div className="signature-box">
      <div className="signature-heading">
        <strong>{label}</strong>
        <span>Not mandatory</span>
      </div>
      <canvas
        ref={canvasRef}
        width="520"
        height="150"
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerLeave={end}
      />
      <button type="button" className="secondary-button" onClick={clear}>Clear signature</button>
    </div>
  );
}
// date-display-ddmmyyyy-v1
