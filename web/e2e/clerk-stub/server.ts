/* Browser tests only: stands in for @clerk/nextjs/server. See next.config.ts. */
import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

export const USER_COOKIE = "e2e-user";

export async function auth() {
  const user = (await cookies()).get(USER_COOKIE)?.value;
  return {
    userId: user ?? null,
    getToken: async () => {
      if (!user) return null;
      const response = await fetch(`${process.env.E2E_ISSUER}/token?user=${encodeURIComponent(user)}`, { cache: "no-store" });
      return ((await response.json()) as { token: string }).token;
    },
  };
}

export function createRouteMatcher(patterns: string[]) {
  const prefixes = patterns.map((pattern) => pattern.replace("(.*)", ""));
  return (request: NextRequest) => prefixes.some((prefix) => request.nextUrl.pathname.startsWith(prefix));
}

class NotSignedIn extends Error {}

type Handler = (auth: { protect: () => Promise<void> }, request: NextRequest) => Promise<void>;

export function clerkMiddleware(handler: Handler, options: { signInUrl: string; signUpUrl: string }) {
  return async (request: NextRequest) => {
    try {
      await handler(
        {
          protect: async () => {
            if (!request.cookies.get(USER_COOKIE)) throw new NotSignedIn();
          },
        },
        request,
      );
    } catch (error) {
      if (error instanceof NotSignedIn) return NextResponse.redirect(new URL(options.signInUrl, request.url));
      throw error;
    }
    return NextResponse.next();
  };
}
