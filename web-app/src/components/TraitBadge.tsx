import type { Trait } from "../types";

const TRAIT_STYLES: Record<string, string> = {
  Vegetarian: "bg-green-badge/50 text-green-badge-text border-green-badge-text/10",
  Vegan: "bg-green-badge/50 text-green-badge-text border-green-badge-text/10",
  Halal: "bg-teal-badge/50 text-teal-badge-text border-teal-badge-text/10",
  Kosher: "bg-teal-badge/50 text-teal-badge-text border-teal-badge-text/10",
  GlutenFree: "bg-amber-badge/50 text-amber-badge-text border-amber-badge-text/10",
  ContainsNuts: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsPeanuts: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsTreeNuts: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsDairy: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsEggs: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsSoy: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsWheat: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsFish: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsShellfish: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  ContainsSesame: "bg-rose-badge/50 text-rose-badge-text border-rose-badge-text/10",
  Spicy: "bg-red-badge/50 text-red-badge-text border-red-badge-text/10",
  LocalProcurement: "bg-mauve-badge/50 text-mauve-badge-text border-mauve-badge-text/10",
  FarmToTable: "bg-mauve-badge/50 text-mauve-badge-text border-mauve-badge-text/10",
  Humane: "bg-mauve-badge/50 text-mauve-badge-text border-mauve-badge-text/10",
};

const DEFAULT_STYLE = "bg-surface-4/50 text-text-secondary border-border-subtle";

function normalize(name: string): string {
  return name.replace(/[\s-]/g, "").toLowerCase();
}

function getTraitStyle(name: string): string {
  for (const [key, style] of Object.entries(TRAIT_STYLES)) {
    if (normalize(name).includes(normalize(key))) {
      return style;
    }
  }
  return DEFAULT_STYLE;
}

export default function TraitBadge({ trait }: { trait: Trait }) {
  const styleClass = getTraitStyle(trait.name);
  return (
    <span
      className={`inline-block font-body text-[10px] font-medium tracking-wide px-2 py-0.5 rounded-full border ${styleClass}`}
    >
      {trait.name}
    </span>
  );
}