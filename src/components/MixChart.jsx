import React from 'react';
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip
} from 'recharts';

export default function MixChart({ selectedHex }) {
  // Extract scores or default to Povo average values
  const resScore = selectedHex ? parseFloat(selectedHex.res_score || 0) : 0.42;
  const commScore = selectedHex ? parseFloat(selectedHex.comm_score || 0) : 0.38;
  const occaScore = selectedHex ? parseFloat(selectedHex.occa_score || 0) : 0.56;

  const data = [
    { subject: 'Residenti', score: Math.round(resScore * 100), fullMark: 100 },
    { subject: 'Pendolari', score: Math.round(commScore * 100), fullMark: 100 },
    { subject: 'Occasionali', score: Math.round(occaScore * 100), fullMark: 100 }
  ];

  return (
    <div className="w-full h-64 relative flex flex-col items-center justify-center bg-slate-900/40 rounded-xl p-2 border border-slate-700/50">
      <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1 self-start px-2">
        {selectedHex ? 'Profilo Co-presenza Esagone' : 'Profilo Medio Circoscrizione'}
      </div>
      
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="rgba(255, 255, 255, 0.15)" />
          <PolarAngleAxis 
            dataKey="subject" 
            tick={{ fill: '#e2e8f0', fontSize: 12, fontWeight: 600 }} 
          />
          <PolarRadiusAxis 
            angle={30} 
            domain={[0, 100]} 
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            stroke="rgba(255, 255, 255, 0.1)"
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: 'rgba(15, 23, 42, 0.95)', 
              borderColor: 'rgba(99, 102, 241, 0.4)',
              borderRadius: '8px',
              color: '#f8fafc'
            }} 
            formatter={(value) => [`${value}%`, 'Score Normalizzato']}
          />
          <Radar
            name="Mixità"
            dataKey="score"
            stroke="#6366f1"
            fill="#818cf8"
            fillOpacity={0.55}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
