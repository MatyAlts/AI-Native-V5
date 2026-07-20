import { SignedIn, SignedOut } from "@clerk/clerk-react"
import { LoginPage } from "./pages/LoginPage"
import { Router } from "./router/Router"

const HAS_CLERK = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

export default function App() {
  if (!HAS_CLERK) return <Router />
  return (
    <>
      <SignedIn>
        <Router />
      </SignedIn>
      <SignedOut>
        <LoginPage />
      </SignedOut>
    </>
  )
}

