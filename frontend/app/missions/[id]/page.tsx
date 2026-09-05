import { MissionDetail } from "@/components/MissionDetail";

export default async function MissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MissionDetail key={id} missionId={id} />;
}
