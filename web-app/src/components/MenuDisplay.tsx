import type { LocationMenuData } from "../types";
import MealSection from "./MealSection";

export default function MenuDisplay({ data }: { data: LocationMenuData | null }) {
  if (!data || !data.diningCourtByName) {
    return (
      <div className="text-center py-16">
        <p className="font-display text-xl text-text-secondary">No menu data available</p>
        <p className="font-body text-sm text-text-muted mt-2">
          This dining court may not exist or the date may be invalid.
        </p>
      </div>
    );
  }

  const court = data.diningCourtByName;

  if (!court.dailyMenu) {
    return (
      <div className="text-center py-16">
        <p className="font-display text-2xl text-text-primary mb-2">{court.formalName}</p>
        <div className="w-12 h-px bg-border-gold mx-auto mb-4" />
        <p className="font-body text-text-secondary">
          No menu available for this date. The dining court may be closed.
        </p>
      </div>
    );
  }

  const meals = court.dailyMenu.meals;

  if (meals.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="font-display text-2xl text-text-primary mb-2">{court.formalName}</p>
        <div className="w-12 h-px bg-border-gold mx-auto mb-4" />
        <p className="font-body text-text-secondary">No meals found for this date.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h2 className="font-display text-3xl font-bold text-text-primary">
          {court.formalName}
        </h2>
        <div className="w-16 h-0.5 bg-gradient-to-r from-gold to-transparent mt-3" />
      </div>
      <div className="space-y-8">
        {meals.map((meal, i) => (
          <MealSection key={meal.name} meal={meal} index={i} />
        ))}
      </div>
    </div>
  );
}