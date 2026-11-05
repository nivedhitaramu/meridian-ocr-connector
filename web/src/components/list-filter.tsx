import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** A plain GET form, so a search has its own address and works before any script loads. */
export function ListFilter({
  action,
  organizationId,
  searchLabel,
  statusLabel,
  q,
  status,
  statuses,
}: {
  action: string;
  organizationId: string;
  searchLabel: string;
  statusLabel: string;
  q: string;
  status: string;
  statuses: [string, string][];
}) {
  return (
    <form action={action} className="flex flex-wrap items-end gap-3">
      <input type="hidden" name="org" value={organizationId} />
      <div className="w-full space-y-1 sm:w-64">
        <label htmlFor="filter-q" className="text-sm font-medium">
          {searchLabel}
        </label>
        <Input id="filter-q" name="q" defaultValue={q} maxLength={100} />
      </div>
      <div className="w-full space-y-1 sm:w-48">
        <label htmlFor="filter-status" className="text-sm font-medium">
          {statusLabel}
        </label>
        <select
          id="filter-status"
          name="status"
          defaultValue={status}
          className="border-input focus-visible:border-ring focus-visible:ring-ring/50 h-8 w-full rounded-lg border bg-transparent px-2 text-base outline-none focus-visible:ring-3 md:text-sm"
        >
          <option value="">All</option>
          {statuses.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" variant="outline">
        Apply
      </Button>
      {q || status ? (
        // A full page load, like the form itself, so the search box empties too.
        <a href={`${action}?org=${organizationId}`} className={buttonVariants({ variant: "ghost" })}>
          Clear
        </a>
      ) : null}
    </form>
  );
}
