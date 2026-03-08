import { Activity, Database } from "lucide-react";
import { CrawlerTaskBuilder } from "@/components/features/CrawlerTaskBuilder";
import { ServerStatus } from "@/components/features/ServerStatus";
import { DashboardTasks } from "@/components/features/DashboardTasks";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  return (
    <div className="space-y-6 pb-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
      <PageHeader
        eyebrow="Operations Console"
        icon={Activity}
        title="采集控制台"
        description="创建任务并查看状态。"
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,0.95fr)]">
        <CrawlerTaskBuilder />

        <div className="space-y-6">
          <ServerStatus />

          <Card className="rounded-[1.5rem] border-border/60 bg-card/90 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-xl">
                <Database className="h-5 w-5 text-primary" />
                最近任务
              </CardTitle>
            </CardHeader>
            <CardContent>
              <DashboardTasks />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
