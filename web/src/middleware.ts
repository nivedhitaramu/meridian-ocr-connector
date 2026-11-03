import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtected = createRouteMatcher(["/workspace(.*)"]);

export default clerkMiddleware(
  async (auth, request) => {
    if (isProtected(request)) {
      await auth.protect();
    }
  },
  { signInUrl: "/sign-in", signUpUrl: "/sign-up" },
);

// Only routes that need sign-in state, so the public landing page runs without Clerk's redirects.
export const config = {
  matcher: ["/workspace/:path*", "/sign-in/:path*", "/sign-up/:path*"],
};
