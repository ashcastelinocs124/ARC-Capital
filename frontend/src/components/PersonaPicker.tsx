import { useEffect, useState } from "react";
import { listPersonas } from "../api/personas";
import type { PersonaCard } from "../api/types";

interface Props {
  selected: string | null;
  onChange: (personaId: string) => void;
}

export function PersonaPicker({ selected, onChange }: Props) {
  const [personas, setPersonas] = useState<PersonaCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPersonas()
      .then(setPersonas)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <div className="text-red-500">Error loading personas: {error}</div>;
  }
  if (personas === null) {
    return <div className="text-gray-500">Loading personas...</div>;
  }
  if (personas.length === 0) {
    return (
      <div className="text-gray-500">
        No personas built yet. Run <code>ckm persona-build</code>.
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {personas.map((p) => {
        const isSelected = p.persona_id === selected;
        return (
          <li
            key={p.persona_id}
            data-testid="persona-option"
            data-selected={isSelected}
            onClick={() => onChange(p.persona_id)}
            className={`cursor-pointer rounded-md border px-3 py-2 transition ${
              isSelected
                ? "border-blue-500 bg-blue-50"
                : "border-gray-200 hover:border-gray-400"
            }`}
          >
            <div className="font-semibold">{p.full_name}</div>
            <div className="text-xs text-gray-500">{p.role}</div>
          </li>
        );
      })}
    </ul>
  );
}
