// Official provider pages checked on 2026-10-24. These optional links are separate
// from the planner's verified course selections, costs and completion estimates.
export interface CourseSource { provider: string; title: string; url: string; catalog?: boolean }
const thinking: CourseSource[] = [
  { provider: 'HP LIFE', title: 'Critical Thinking in the AI Era', url: 'https://www.life-global.org/course/439' },
  { provider: 'Saylor University', title: 'Introduction to Critical Thinking and Logic', url: 'https://learn.saylor.org/course/phil102' },
  { provider: 'edX', title: 'Critical thinking courses', url: 'https://www.edx.org/learn/critical-thinking-skills', catalog: true },
];
const communication: CourseSource[] = [
  { provider: 'Coursera · Wharton', title: 'Improving Communication Skills', url: 'https://www.coursera.org/learn/wharton-communication-skills' },
  { provider: 'HP LIFE', title: 'Effective Presentations', url: 'https://www.life-global.org/course/12-effective-presentations' },
  { provider: 'edX', title: 'Communication courses', url: 'https://www.edx.org/learn/communication', catalog: true },
];
const learning: CourseSource[] = [
  { provider: 'Coursera', title: 'Learning How to Learn', url: 'https://www.coursera.org/learn/learning-how-to-learn' },
  ...thinking.slice(0, 2),
];
const general: CourseSource[] = [
  { provider: 'HP LIFE', title: 'Business and digital skills', url: 'https://www.life-global.org/', catalog: true },
  { provider: 'Coursera', title: 'Personal development courses', url: 'https://www.coursera.org/browse/business/personal-development', catalog: true },
  { provider: 'IBM SkillsBuild', title: 'Career and technology learning', url: 'https://skillsbuild.org/', catalog: true },
];

export function courseSources(skillLabels: string[]): CourseSource[] {
  const topic = skillLabels.join(' ').toLowerCase();
  if (/python|programming|software|sql|database|power bi|excel|data analysis/.test(topic)) return [
    { provider: 'Microsoft Learn', title: 'Find technical training', url: `https://learn.microsoft.com/en-us/training/browse/?terms=${encodeURIComponent(skillLabels.join(' '))}`, catalog: true },
    ...(topic.includes('python') ? [{ provider: 'Microsoft Learn', title: 'Write your first Python code', url: 'https://learn.microsoft.com/en-us/training/modules/write-first-python-code/' }] : []),
    general[2],
  ];
  if (/math|quantitative|statistics/.test(topic)) return [
    { provider: 'Khan Academy', title: 'Math courses and practice', url: 'https://www.khanacademy.org/math', catalog: true },
    { provider: 'Coursera', title: 'Math and logic courses', url: 'https://www.coursera.org/browse/math-and-logic', catalog: true },
    { provider: 'edX', title: 'Math courses', url: 'https://www.edx.org/learn/math', catalog: true },
  ];
  if (/reading/.test(topic)) return general;
  if (/critical thinking|judgment|decision|problem solving|systems analysis|systems evaluation/.test(topic)) return thinking;
  if (/listening|speaking|writing|reading|communication|persuasion|negotiation|social perceptiveness/.test(topic)) return communication;
  if (/active learning|learning strategies|monitoring|time management/.test(topic)) return learning;
  if (/leadership|personnel|coordination|management/.test(topic)) return [
    { provider: 'HP LIFE', title: 'Effective Leadership', url: 'https://www.life-global.org/en/course/13-effective-' },
    communication[0], general[1],
  ];
  return general;
}
