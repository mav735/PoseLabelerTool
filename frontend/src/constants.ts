export const NUM_KPTS = 15;
export const KPT_NAMES = ["hd","ch","pl","ls","rs","lh","rh","lw","rw","lf","rf","le","re","lk","rk"];
export const SKELETON: [number, number][] = [
  [0,1],[1,2],[1,3],[1,4],[3,11],[11,7],[4,12],[12,8],[2,5],[2,6],[5,13],[13,9],[6,14],[14,10],
];
export const FLIP_IDX = [0,1,2,4,3,6,5,8,7,10,9,12,11,14,13];
export const GT_COLOR = "rgb(0,200,200)";
export const PRED_COLOR = "rgb(255,0,255)";
export const VIS_COLORS: [string, string, string] = ["rgb(128,128,128)", "rgb(255,165,0)", "rgb(0,255,0)"];
