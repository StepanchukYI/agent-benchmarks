import type { ReactNode } from "react";

type PageShellProps = {
  title: string;
  children: ReactNode;
};

export default function PageShell({ title, children }: PageShellProps): JSX.Element {
  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      </header>
      <div>{children}</div>
    </section>
  );
}
