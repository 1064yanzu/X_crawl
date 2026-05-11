import { Activity } from "lucide-react";
import { CrawlerTaskBuilder } from "@/components/features/CrawlerTaskBuilder";
import { ServerStatus } from "@/components/features/ServerStatus";
import { DashboardTasks } from "@/components/features/DashboardTasks";
import { DashboardLiveRates } from "@/components/features/DashboardLiveRates";
import { PageHeader } from "@/components/ui/page-header";

export default function Home() {
    return (
        <article className="space-y-14 pb-16">
            <div className="editorial-rise">
                <PageHeader
                    eyebrow="Issue 01 · Console"
                    icon={Activity}
                    title="采集控制台"
                    description="创建任务、监听进度、收纳成果。先确认环境，再开始。"
                />
            </div>

            <section className="editorial-rise editorial-rise-2 grid gap-14 xl:grid-cols-[minmax(0,1.6fr)_minmax(300px,0.9fr)]">
                <div className="min-w-0 space-y-10">
                    <CrawlerTaskBuilder />
                </div>

                <aside className="flex flex-col gap-12 xl:pl-2">
                    <ServerStatus />

                    <DashboardLiveRates />

                    <section aria-labelledby="recent-tasks-heading" className="space-y-4">
                        <div className="flex items-baseline justify-between gap-3">
                            <div>
                                <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-[color:var(--fg-subtle)]">
                                    Recent dispatches
                                </p>
                                <h2
                                    id="recent-tasks-heading"
                                    className="mt-1 font-serif text-[1.5rem] font-medium leading-tight tracking-tight text-foreground"
                                >
                                    最近任务
                                </h2>
                            </div>
                        </div>
                        <hr className="border-[var(--line)]" />
                        <DashboardTasks />
                    </section>
                </aside>
            </section>
        </article>
    );
}
