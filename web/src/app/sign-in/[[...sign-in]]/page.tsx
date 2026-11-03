import { SignIn } from "@clerk/nextjs";

import { AuthFrame } from "@/components/auth-frame";

export const metadata = { title: "Sign in | Meridian Intelligence" };

export default function SignInPage() {
  return (
    <AuthFrame>
      <SignIn signUpUrl="/sign-up" fallbackRedirectUrl="/workspace" />
    </AuthFrame>
  );
}
