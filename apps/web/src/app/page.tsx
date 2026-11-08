import { HealthStatus } from "@/components/HealthStatus";

export default function Home() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-bold">STENTOR</h1>
      <p className="mb-6 mt-1 text-neutral-700">
        Every warning, in every language, verified before it is sent.
      </p>
      <HealthStatus />
    </main>
  );
}
