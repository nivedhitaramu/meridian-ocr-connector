import { SignUp } from "@clerk/nextjs";

import { AuthFrame } from "@/components/auth-frame";

export const metadata = { title: "Create your account | Meridian Intelligence" };

export default function SignUpPage() {
  return (
    <AuthFrame>
      <SignUp signInUrl="/sign-in" fallbackRedirectUrl="/workspace" />
    </AuthFrame>
  );
}
