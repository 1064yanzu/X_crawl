import { CrawlerTaskBuilder } from "@/components/features/CrawlerTaskBuilder";
import { ServerStatus } from "@/components/features/ServerStatus";
import { DashboardTasks } from "@/components/features/DashboardTasks";
import { Activity, Database } from "lucide-react";

export default function Home() {
  return (
    <div className="w-full space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out py-6 pb-24">
      {/* Header section with Server Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-border/40 pb-6">
        <div className="space-y-2 flex-1 min-w-[250px]">
          <h1 className="text-3xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Activity className="w-7 h-7 text-primary shrink-0" />
            <span className="shrink-0">采集控制台</span>
          </h1>
          <p className="text-muted-foreground mr-4">
            监控系统运行状态并实时创建、下发新型数据采集队列。
          </p>
        </div>

        {/* Health Monitoring Widget */}
        <div className="shrink-0 w-full md:w-auto overflow-x-auto pb-2 md:pb-0">
          <ServerStatus />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 pt-4">
        {/* Main Task Builder Section (User Operations) */}
        <div className="lg:col-span-7 flex justify-center">
          <CrawlerTaskBuilder />
        </div>

        {/* Real-time Data & Historical Operations Widget */}
        <div className="lg:col-span-5 space-y-6">
          <div className="bg-card border rounded-2xl p-6 shadow-sm">
            <h3 className="font-semibold text-lg flex items-center gap-2 mb-4">
              <Database className="w-5 h-5 text-muted-foreground" />
              数据大盘 (Data Monitor)
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              全局监控正在执行的任务及最近历史足迹。
            </p>
            <DashboardTasks />
          </div>
        </div>
      </div>
    </div>
  );
}

