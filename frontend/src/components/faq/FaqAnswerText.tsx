import React from "react";

type Props = {
  text: string;
  compact?: boolean;
};

function inlineMarkup(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${index}-${part}`}>{part.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={`${index}-${part}`}>{part}</React.Fragment>;
  });
}

function normalizeLine(line: string): string {
  return line.replace(/\s+$/g, "");
}

export function FaqAnswerText(props: Props) {
  const blocks = props.text
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div
      className={
        props.compact
          ? "efhc-faq-answer-content is-compact"
          : "efhc-faq-answer-content"
      }
    >
      {blocks.map((block, blockIndex) => {
        const lines = block.split("\n").map(normalizeLine).filter(Boolean);
        const list = lines.length > 0 && lines.every((line) => /^[-*•]\s+/.test(line));
        if (list) {
          return (
            <ul key={`list-${blockIndex}`}>
              {lines.map((line, lineIndex) => (
                <li key={`${blockIndex}-${lineIndex}`}>
                  {inlineMarkup(line.replace(/^[-*•]\s+/, ""))}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={`paragraph-${blockIndex}`}>
            {lines.map((line, lineIndex) => (
              <React.Fragment key={`${blockIndex}-${lineIndex}`}>
                {lineIndex > 0 ? <br /> : null}
                {inlineMarkup(line)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
