from flask import Flask, render_template, request, jsonify, send_file, session
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import plotly
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import io
from werkzeug.security import generate_password_hash, check_password_hash
warnings.filterwarnings('ignore')

app = Flask(__name__)
app.secret_key = 'carbon_footprint_platform_secret_key_2024'

# ==================== 1. 静态排放因子数据库 ====================
class EmissionFactorDatabase:
    """静态排放因子数据库"""
    
    def __init__(self):
        # 燃料排放因子 (kgCO2/单位)
        self.fuel_factors = {
            '燃煤': {'因子': 2.64, '单位': '吨CO2/吨煤', '来源': 'IPCC 2006'},
            '天然气': {'因子': 2.16, '单位': '吨CO2/吨标准煤', '来源': 'IPCC 2006'},
            '汽油': {'因子': 2.93, '单位': '吨CO2/吨', '来源': 'IPCC 2006'},
            '柴油': {'因子': 3.10, '单位': '吨CO2/吨', '来源': 'IPCC 2006'},
            '燃料油': {'因子': 3.24, '单位': '吨CO2/吨', '来源': 'IPCC 2006'},
            '液化石油气': {'因子': 3.03, '单位': '吨CO2/吨', '来源': 'IPCC 2006'},
        }
        
        # 区域电网平均排放因子 (kgCO2/kWh) - 2024年数据
        self.grid_factors = {
            '华北区域电网': 0.9419,
            '东北区域电网': 1.0821,
            '华东区域电网': 0.7921,
            '华中区域电网': 0.8587,
            '西北区域电网': 0.9428,
            '南方区域电网': 0.8042,
            '北京': 0.7921,
            '上海': 0.7921,
            '江苏': 0.7921,
            '浙江': 0.7921,
            '广东': 0.8042,
            '山东': 0.9419,
        }
        
        # 碳市场价格 (元/吨CO2)
        self.carbon_prices = {
            '中国碳配额(CEA)': 60.0,  # 元/吨CO2
            '中国核证减排量(CCER)': 40.0,  # 元/吨CO2
            '欧盟碳配额(EUA)': 80.0,  # 欧元/吨CO2
        }
        
        # 行业基准值
        self.industry_benchmarks = {
            '钢铁': {
                '螺纹钢': {'单位能耗': 570, '单位': 'kgce/吨'},
                '热轧板': {'单位能耗': 620, '单位': 'kgce/吨'},
            },
            '水泥': {
                '水泥熟料': {'单位能耗': 110, '单位': 'kgce/吨'},
                '普通硅酸盐水泥': {'单位能耗': 90, '单位': 'kgce/吨'},
            },
            '电解铝': {
                '原铝': {'单位能耗': 13500, '单位': 'kWh/吨'},
            },
            '化肥': {
                '尿素': {'单位能耗': 1.2, '单位': '吨标准煤/吨'},
                '合成氨': {'单位能耗': 1.5, '单位': '吨标准煤/吨'},
            }
        }

# ==================== 2. 动态电碳因子模拟器 ====================
class DynamicCarbonFactorSimulator:
    """模拟动态电碳因子（三种置信度）"""
    
    def __init__(self):
        self.daily_factors = self._generate_daily_factors()
        
    def _generate_daily_factors(self):
        """生成一年的日级动态电碳因子"""
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='D')
        
        # 基础趋势 - 夏季和冬季高，春秋低
        seasonal = 0.15 * np.sin(2 * np.pi * dates.dayofyear / 365 - np.pi/2)
        
        # 工作日/节假日效应
        weekday_effect = np.where(dates.weekday < 5, 0.05, -0.03)
        
        # 三种置信度
        daily_factors = pd.DataFrame({
            'date': dates,
            'low_confidence': 0.85 * (1 + seasonal + np.random.normal(0, 0.12, len(dates))),
            'medium_confidence': 0.80 * (1 + 0.8*seasonal + 0.5*weekday_effect + np.random.normal(0, 0.08, len(dates))),
            'high_confidence': 0.78 * (1 + 0.6*seasonal + 0.3*weekday_effect + np.random.normal(0, 0.05, len(dates))),
        })
        
        return daily_factors.set_index('date')
    
    def get_factor(self, date_str, confidence_level='medium'):
        """获取指定日期的电碳因子"""
        try:
            date = pd.to_datetime(date_str)
            if confidence_level == 'low':
                return float(self.daily_factors.loc[date, 'low_confidence'])
            elif confidence_level == 'high':
                return float(self.daily_factors.loc[date, 'high_confidence'])
            else:
                return float(self.daily_factors.loc[date, 'medium_confidence'])
        except:
            return 0.8  # 默认值

# ==================== 3. 核心计算器 ====================
class CarbonFootprintCalculator:
    """碳足迹计算器"""
    
    def __init__(self):
        self.db = EmissionFactorDatabase()
        self.simulator = DynamicCarbonFactorSimulator()
    
    def calculate_scope1(self, fuel_data):
        """计算Scope 1排放"""
        details = []
        total = 0
        
        for fuel in fuel_data:
            fuel_type = fuel.get('fuel_type', '')
            consumption = float(fuel.get('consumption', 0))
            unit = fuel.get('unit', '吨')
            
            if fuel_type in self.db.fuel_factors:
                factor = self.db.fuel_factors[fuel_type]['因子']
                emissions = consumption * factor
                total += emissions
                
                details.append({
                    'fuel_type': fuel_type,
                    'consumption': round(consumption, 2),
                    'unit': unit,
                    'emission_factor': factor,
                    'emissions_ton': round(emissions, 2)
                })
        
        return {'total': round(total, 2), 'details': details}
    
    def calculate_scope2(self, electricity_data, region, confidence_level='medium', use_dynamic=True):
        """计算Scope 2排放"""
        details = []
        total = 0
        
        # 处理年度总量
        if isinstance(electricity_data, dict) and 'annual_consumption_kwh' in electricity_data:
            consumption = float(electricity_data['annual_consumption_kwh'])
            
            if use_dynamic:
                # 使用年均动态因子
                factors = self.simulator.get_yearly_factors(confidence_level)
                avg_factor = float(factors.mean())
            else:
                # 使用静态因子
                avg_factor = self.db.grid_factors.get(region, 0.8)
            
            emissions = consumption * avg_factor / 1000
            total = emissions
            
            details.append({
                'method': 'annual_total',
                'consumption_kwh': round(consumption, 2),
                'carbon_factor': round(avg_factor, 4),
                'emissions_ton': round(emissions, 2)
            })
        
        # 处理日级数据
        elif isinstance(electricity_data, list):
            for day_data in electricity_data:
                date_str = day_data.get('date', '')
                consumption = float(day_data.get('consumption_kwh', 0))
                
                if use_dynamic:
                    carbon_factor = self.simulator.get_factor(date_str, confidence_level)
                else:
                    carbon_factor = self.db.grid_factors.get(region, 0.8)
                
                daily_emissions = consumption * carbon_factor / 1000
                total += daily_emissions
                
                details.append({
                    'date': date_str,
                    'consumption_kwh': round(consumption, 2),
                    'carbon_factor': round(carbon_factor, 4),
                    'emissions_ton': round(daily_emissions, 2)
                })
        
        return {
            'total': round(total, 2),
            'details': details,
            'use_dynamic': use_dynamic,
            'confidence_level': confidence_level
        }
    
    def calculate_cbam_tax(self, product_footprint, export_data, 
                          eu_carbon_price=80, china_carbon_price=60, free_allowance_rate=0.1):
        """计算CBAM税负"""
        carbon_intensity = product_footprint
        export_volume = float(export_data.get('export_volume', 0))
        unit = export_data.get('unit', '吨')
        
        # CBAM税计算公式
        if eu_carbon_price > china_carbon_price:
            tax_per_unit = (eu_carbon_price - china_carbon_price) * carbon_intensity * (1 - free_allowance_rate)
        else:
            tax_per_unit = 0
        
        total_tax = tax_per_unit * export_volume
        
        # 汇率转换 (1欧元 ≈ 7.8人民币)
        exchange_rate = 7.8
        
        return {
            'product_carbon_intensity': round(carbon_intensity, 4),
            'export_volume': export_volume,
            'export_unit': unit,
            'eu_carbon_price_eur': eu_carbon_price,
            'china_carbon_price_eur': china_carbon_price,
            'free_allowance_rate': round(free_allowance_rate * 100, 1),
            'tax_per_unit_eur': round(tax_per_unit, 2),
            'total_tax_eur': round(total_tax, 2),
            'total_tax_cny': round(total_tax * exchange_rate, 2)
        }
    
    def generate_heatmap_data(self, start_date='2024-01-01', days=365):
        """生成时空碳强度热力图数据"""
        regions = ['北京', '上海', '江苏', '浙江', '广东', '山东']
        dates = pd.date_range(start=start_date, periods=days, freq='D')
        
        data = []
        for date in dates:
            for region in regions:
                # 模拟不同地区、不同时间的碳强度
                base_factor = self.db.grid_factors.get(region, 0.8)
                
                # 添加季节性和随机波动
                seasonal = 0.2 * np.sin(2 * np.pi * date.dayofyear / 365)
                weekday_effect = 0.1 if date.weekday() < 5 else -0.05
                random_factor = np.random.normal(0, 0.1)
                
                carbon_factor = base_factor * (1 + 0.6*seasonal + 0.3*weekday_effect + 0.1*random_factor)
                
                data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'region': region,
                    'carbon_factor': round(carbon_factor, 4),
                    'level': self._get_carbon_level(carbon_factor)
                })
        
        return data
    
    def _get_carbon_level(self, factor):
        """根据碳因子值划分等级"""
        if factor < 0.7:
            return '非常清洁'
        elif factor < 0.8:
            return '清洁'
        elif factor < 0.9:
            return '中等'
        elif factor < 1.0:
            return '较高'
        else:
            return '很高'

# ==================== 4. Flask路由 ====================
calculator = CarbonFootprintCalculator()

@app.route('/')
def home():
    """首页"""
    return render_template('index.html')

@app.route('/calculator')
def calculator_page():
    """碳足迹计算器页面"""
    return render_template('calculator.html')

@app.route('/api/calculate', methods=['POST'])
def api_calculate():
    """API计算接口"""
    try:
        data = request.json
        
        # 1. 计算Scope 1
        scope1_result = calculator.calculate_scope1(data.get('fuel_data', []))
        
        # 2. 计算Scope 2
        scope2_result = calculator.calculate_scope2(
            electricity_data=data.get('electricity_data', {}),
            region=data.get('region', '华东区域电网'),
            confidence_level=data.get('confidence_level', 'medium'),
            use_dynamic=data.get('use_dynamic', True)
        )
        
        # 3. 计算总碳足迹
        total_emissions = scope1_result['total'] + scope2_result['total']
        
        # 4. 计算产品碳足迹
        production_data = data.get('production_data', {})
        annual_output = float(production_data.get('output', 1))
        product_footprint = total_emissions / annual_output if annual_output > 0 else 0
        
        # 5. 计算CBAM税负
        cbam_result = None
        export_data = data.get('export_data', {})
        if export_data and float(export_data.get('export_volume', 0)) > 0:
            cbam_result = calculator.calculate_cbam_tax(
                product_footprint=product_footprint,
                export_data=export_data
            )
        
        # 6. 准备返回数据
        response = {
            'success': True,
            'data': {
                'company_info': data.get('company_info', {}),
                'scope1': scope1_result,
                'scope2': scope2_result,
                'total_emissions': round(total_emissions, 2),
                'product_footprint': round(product_footprint, 4),
                'production_data': production_data,
                'cbam_result': cbam_result,
                'calculation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': '计算过程中出现错误'
        }), 400

@app.route('/api/heatmap')
def api_heatmap():
    """获取热力图数据"""
    try:
        data = calculator.generate_heatmap_data()
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/emission_factors')
def api_emission_factors():
    """获取排放因子数据"""
    try:
        db = EmissionFactorDatabase()
        return jsonify({
            'success': True,
            'data': {
                'fuel_factors': db.fuel_factors,
                'grid_factors': db.grid_factors,
                'carbon_prices': db.carbon_prices
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/results')
def results_page():
    """结果展示页面"""
    return render_template('results.html')

@app.route('/api/scenarios', methods=['POST'])
def api_scenarios():
    """多情景模拟分析"""
    try:
        data = request.json
        base_result = data.get('base_result', {})
        scenarios = data.get('scenarios', [])
        
        results = []
        for scenario in scenarios:
            # 这里实现具体的情景模拟逻辑
            result = {
                'scenario_name': scenario.get('name', ''),
                'emissions_reduction': round(np.random.uniform(5, 30), 1),  # 模拟减排比例
                'cbam_tax_saving': round(np.random.uniform(1000, 50000), 2),  # 模拟税负节省
                'roi_years': round(np.random.uniform(2, 8), 1)  # 模拟投资回报年限
            }
            results.append(result)
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/download_report', methods=['POST'])
def download_report():
    """下载报告"""
    try:
        data = request.json
        
        # 生成报告文本
        report_text = f"""
        企业碳足迹计算报告
        ====================
        
        企业名称：{data.get('company_name', '')}
        计算时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        1. 排放总量
        ----------
        Scope 1 排放：{data.get('scope1_total', 0)} 吨CO₂
        Scope 2 排放：{data.get('scope2_total', 0)} 吨CO₂
        总排放量：{data.get('total_emissions', 0)} 吨CO₂
        
        2. 产品碳足迹
        ----------
        产品名称：{data.get('product_name', '')}
        产量：{data.get('annual_output', 0)} {data.get('output_unit', '吨')}
        产品碳足迹：{data.get('product_footprint', 0)} 吨CO₂/{data.get('output_unit', '吨')}
        
        3. CBAM税负分析
        ------------
        """
        
        if data.get('cbam_result'):
            cbam = data['cbam_result']
            report_text += f"""
            出口产品：{cbam.get('export_product', '')}
            出口量：{cbam.get('export_volume', 0)} {cbam.get('export_unit', '吨')}
            预计CBAM税负：{cbam.get('total_tax_cny', 0)} 元人民币
            """
        
        report_text += f"""
        
        4. 减排建议
        ----------
        {data.get('recommendations', '请根据具体情况制定减排措施。')}
        
        报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        # 创建内存文件
        mem_file = io.BytesIO()
        mem_file.write(report_text.encode('utf-8'))
        mem_file.seek(0)
        
        return send_file(
            mem_file,
            as_attachment=True,
            download_name=f'碳足迹报告_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt',
            mimetype='text/plain'
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== 5. 错误处理 ====================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='页面未找到'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('error.html', error='服务器内部错误'), 500

# ==================== 6. 启动应用 ====================
if __name__ == '__main__':
    print("=" * 60)
    print("企业碳足迹计算平台")
    print("=" * 60)
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)