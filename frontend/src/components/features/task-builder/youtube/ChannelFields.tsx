"use client";

import * as React from "react";
import { Link2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { SectionTitle } from "@/components/features/task-builder/TaskBuilderSection";

interface Props {
    channelInput: string;
    onChannelInputChange: (value: string) => void;
}

export function YouTubeChannelFields(props: Props) {
    return (
        <section className="space-y-4 rounded-[1.25rem] border border-border/60 bg-background/70 p-5 shadow-sm">
            <SectionTitle
                title="频道视频列表"
                description="按频道主页 uploads 列表按时间倒序抓全量视频，配额消耗远低于关键词搜索。"
            />

            <label className="flex flex-col gap-1.5 text-sm">
                <span className="font-medium text-foreground flex items-center gap-1.5">
                    <Link2 className="h-3.5 w-3.5" /> 频道标识
                </span>
                <Input
                    value={props.channelInput}
                    onChange={(event) => props.onChannelInputChange(event.target.value)}
                    placeholder="例如：@GoogleDevelopers / UC_x5XG1OV2P6uZZ5FSM9Ttw / 完整频道主页 URL"
                    className="h-11 rounded-xl"
                />
                <span className="text-xs text-muted-foreground">
                    支持三种输入：<code>@handle</code>、<code>UC…</code> 频道 ID、YouTube 频道主页完整 URL。后端会自动解析为频道 ID 并抓取 uploads 播放列表。
                </span>
            </label>
        </section>
    );
}
