"use client";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";

export default function WorkspaceError({ reset }: { reset: () => void }) {
  return (
    <ErrorState title="We couldn't load your workspace">
      <p className="mb-4">Check that the API is running, then try again.</p>
      <Button variant="outline" onClick={reset}>
        Try again
      </Button>
    </ErrorState>
  );
}
