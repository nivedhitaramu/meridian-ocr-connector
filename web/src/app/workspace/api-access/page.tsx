import { when } from "@/components/labels";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listApiKeys, listDeliveries, listWebhooks } from "@/lib/api";
import { organizationFor } from "@/lib/workspace";

import { AddWebhookForm, CreateKeyForm, KeyActions, RemoveWebhookForm } from "./forms";

export const metadata = { title: "API access | Meridian Intelligence" };

export default async function ApiAccessPage({ searchParams }: { searchParams: Promise<{ org?: string }> }) {
  const { org } = await searchParams;
  const { organizationId, role, context } = await organizationFor(org);
  if (role !== "admin") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">API access</h1>
        <EmptyState title="Only admins can manage API access" />
      </div>
    );
  }
  const [keys, webhooks, deliveries] = await Promise.all([listApiKeys(context), listWebhooks(context), listDeliveries(context)]);
  const activeKeys = keys.filter((key) => !key.revoked_at);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">API access</h1>
        <p className="text-muted-foreground text-sm">Connect another system. A key can submit shipments and read results, with clerk permissions.</p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>API keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <CreateKeyForm organizationId={organizationId} />
          {activeKeys.length === 0 ? (
            <p className="text-muted-foreground text-sm">No active keys.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Starts with</TableHead>
                    <TableHead>Last used</TableHead>
                    <TableHead className="text-right">
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeKeys.map((key) => (
                    <TableRow key={key.id}>
                      <TableCell className="font-medium">{key.name}</TableCell>
                      <TableCell>
                        <code>{key.prefix}</code>
                      </TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">{key.last_used_at ? when(key.last_used_at) : "Never"}</TableCell>
                      <TableCell>
                        <KeyActions organizationId={organizationId} id={key.id} name={key.name} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Webhooks</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <AddWebhookForm organizationId={organizationId} />
          {webhooks.map((webhook) => (
            <div key={webhook.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <code className="break-all">{webhook.url}</code>
              <span className="text-muted-foreground text-xs">{webhook.format === "wms_receipt" ? "Verified receipts" : "Every finished check"}</span>
              <RemoveWebhookForm organizationId={organizationId} id={webhook.id} url={webhook.url} />
            </div>
          ))}
          {deliveries.length > 0 ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Recent delivery</TableHead>
                    <TableHead>Attempts</TableHead>
                    <TableHead>Response</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deliveries.map((delivery) => (
                    <TableRow key={delivery.id}>
                      <TableCell className="capitalize">{delivery.status}</TableCell>
                      <TableCell className="tabular-nums">{delivery.attempts}</TableCell>
                      <TableCell className="tabular-nums">{delivery.response_code ?? "None"}</TableCell>
                      <TableCell className="whitespace-nowrap tabular-nums">{when(delivery.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
